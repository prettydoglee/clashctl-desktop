"""Local-only bridge to the user's existing clashctl installation."""
import collections
import concurrent.futures
import contextlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


class UIError(Exception):
    pass


def run(args, timeout=15, **kwargs):
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired:
        raise UIError('操作超时，请查看日志后重试')
    if result.returncode:
        raise UIError(ANSI.sub('', result.stderr or result.stdout).strip()[-1600:]
                      or '操作未完成')
    return result.stdout.strip()


def atomic_write(path, data):
    fd, name = tempfile.mkstemp(prefix='.clashctl-ui-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(name, str(path))
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name)


class Bridge:
    def __init__(self, home=None):
        self.home = Path(home or os.environ.get('CLASHCTL_HOME', str(Path.home() / '.clashctl')))
        self.yq = self.home / 'bin/yq'
        self.runtime = self.home / 'data/runtime.yaml'
        self.mixin = self.home / 'data/mixin.yaml'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.lock = threading.Lock()
        self.cache_lock = threading.Lock()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=5)
        self.yaml_cache = {}
        self.samples = collections.deque(maxlen=60)
        self.traffic = {'up': 0, 'down': 0}
        self.traffic_at = 0
        self.stop_event = threading.Event()
        self.stream = None
        self.system_cache = (0, None)
        self.state_dir = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'clashctl-ui'
        self.thread = threading.Thread(target=self._traffic_loop, daemon=True)
        self.thread.start()

    def yaml(self, path):
        try:
            stamp = path.stat().st_mtime_ns
        except FileNotFoundError:
            return {}
        with self.cache_lock:
            cached = self.yaml_cache.get(str(path))
            if cached and cached[0] == stamp:
                return cached[1]
            value = json.loads(run([str(self.yq), '-o=json', '.', str(path)])) or {}
            self.yaml_cache[str(path)] = (stamp, value)
            return value

    def request(self, path, method='GET', data=None, stream=False, timeout=8):
        if not self.runtime.is_file() or not self.yq.is_file():
            raise UIError('尚未安装 clashctl，请先在项目目录运行 bash install.sh')
        cfg = self.yaml(self.runtime)
        controller = str(cfg.get('external-controller', '127.0.0.1:9090'))
        port = controller.rsplit(':', 1)[-1]
        if not port.isdigit():
            raise UIError('未找到有效的 Mihomo 控制端口')
        headers = {'Authorization': 'Bearer ' + str(cfg.get('secret') or '')}
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request('http://127.0.0.1:' + port + path,
                                     data=body, headers=headers, method=method)
        try:
            response = self.opener.open(req, timeout=timeout)
            if stream:
                return response
            with response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise UIError('控制接口认证失败，请检查 clashctl 密钥配置')
            try:
                message = json.loads(exc.read()).get('message', '')
            except (ValueError, AttributeError):
                message = ''
            raise UIError(message or '内核接口返回 HTTP ' + str(exc.code))
        except (urllib.error.URLError, TimeoutError, OSError):
            raise UIError('无法连接 Mihomo，请启动内核或检查 clashctl 状态')

    def _traffic_loop(self):
        while not self.stop_event.is_set():
            try:
                with self.request('/traffic', stream=True, timeout=4) as response:
                    self.stream = response
                    while not self.stop_event.is_set():
                        line = response.readline(16384)
                        if not line:
                            break
                        sample = json.loads(line)
                        with self.cache_lock:
                            self.traffic = {'up': max(0, sample.get('up', 0)),
                                            'down': max(0, sample.get('down', 0))}
                            self.traffic_at = time.time()
                            self.samples.append(dict(self.traffic, time=self.traffic_at))
            except (UIError, ValueError, OSError):
                self.stop_event.wait(2)

    def profiles(self):
        data = self.yaml(self.home / 'data/profiles.yaml')
        rows = []
        for item in data.get('profiles') or []:
            info = {k: int(v) for k, v in re.findall(r'(upload|download|total|expire)=(\d+)', str(item.get('userinfo') or ''))}
            url = urllib.parse.urlsplit(str(item.get('url') or ''))
            rows.append({'name': item.get('name', ''), 'updated': item.get('updated', ''),
                         'host': url.hostname or '本地文件', 'usage': info,
                         'active': item.get('name') == data.get('use')})
        return {'current': data.get('use', ''), 'profiles': rows}

    def system_proxy(self, fresh=False):
        cached_at, cached = self.system_cache
        if not fresh and cached is not None and time.monotonic() - cached_at < 5:
            return cached
        try:
            mode = run(['gsettings', 'get', 'org.gnome.system.proxy', 'mode'])
            cfg = self.yaml(self.runtime)
            host = run(['gsettings', 'get', 'org.gnome.system.proxy.http', 'host'])
            port = run(['gsettings', 'get', 'org.gnome.system.proxy.http', 'port'])
            enabled = mode == "'manual'" and host in ("'127.0.0.1'", "'localhost'") and int(port) == cfg.get('mixed-port', cfg.get('port', 7890))
            result = {'available': True, 'enabled': enabled, 'mode': mode.strip("'")}
        except (UIError, OSError, ValueError):
            result = {'available': False, 'enabled': False, 'mode': 'unknown'}
        self.system_cache = (time.monotonic(), result)
        return result

    def set_system_proxy(self, enabled):
        if not self.system_proxy(True)['available']:
            raise UIError('当前桌面不支持 GNOME 系统代理设置')
        keys = [('org.gnome.system.proxy', 'mode')]
        for protocol in ('http', 'https', 'socks'):
            keys += [('org.gnome.system.proxy.' + protocol, key) for key in ('host', 'port')]
        original = [run(['gsettings', 'get', schema, key]) for schema, key in keys]
        backup = self.state_dir / 'proxy-backup.json'
        if enabled:
            cfg = self.yaml(self.runtime)
            port = cfg.get('mixed-port') or cfg.get('port')
            if not port:
                raise UIError('未配置 HTTP / 混合代理端口')
            self.request('/version')
            self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not backup.exists():
                atomic_write(backup, json.dumps(original).encode())
            values = ["'manual'", "'127.0.0.1'", str(port), "'127.0.0.1'", str(port),
                      "'127.0.0.1'", str(cfg.get('socks-port') or port)]
        else:
            values = json.loads(backup.read_text()) if backup.exists() else ["'none'"] + original[1:]
            if not isinstance(values, list) or len(values) != len(keys):
                raise UIError('系统代理备份格式无效')
        try:
            # Configure endpoints before enabling manual mode.
            for i in list(range(1, len(keys))) + [0]:
                schema, key = keys[i]
                run(['gsettings', 'set', schema, key, values[i]])
        except UIError:
            for (schema, key), value in zip(keys, original):
                with contextlib.suppress(UIError):
                    run(['gsettings', 'set', schema, key, value])
            raise
        if not enabled:
            with contextlib.suppress(FileNotFoundError):
                backup.unlink()
        self.system_cache = (0, None)

    def snapshot(self):
        paths = ['/version', '/configs', '/connections', '/proxies']
        pending = [self.pool.submit(self.request, path) for path in paths]
        results, errors = {}, []
        for path, future in zip(paths, pending):
            try:
                results[path] = future.result()
            except UIError as exc:
                errors.append(str(exc))
        with self.cache_lock:
            traffic = dict(self.traffic) if time.time() - self.traffic_at < 4 else {'up': 0, 'down': 0}
            samples = list(self.samples)
        cfg = results.get('/configs', {})
        # Return only displayable fields; controller secrets never leave this process.
        config = {key: cfg.get(key) for key in ('mode', 'mixed-port', 'port', 'socks-port', 'allow-lan', 'ipv6', 'log-level')}
        config['tun'] = {'enable': bool((cfg.get('tun') or {}).get('enable'))}
        connections = results.get('/connections', {})
        return {'online': '/version' in results, 'error': errors[0] if errors else '',
                'version': results.get('/version', {}).get('version', ''),
                'config': config, 'traffic': traffic, 'samples': samples,
                'connections': connections.get('connections') or [],
                'downloadTotal': connections.get('downloadTotal', 0),
                'uploadTotal': connections.get('uploadTotal', 0),
                'memory': connections.get('memory', 0),
                'proxies': results.get('/proxies', {}).get('proxies', {}),
                'subscriptions': self.profiles(), 'systemProxy': self.system_proxy(),
                'directory': str(self.home)}

    def cli(self, args, terminal=False):
        env = dict(os.environ, CLASHCTL_HOME=str(self.home))
        command = ['bash', str(ROOT / 'clashctl-bridge.sh')] + args
        if terminal:
            subprocess.Popen(['x-terminal-emulator', '-e'] + command,
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return {'terminal': True, 'message': '已打开 clashctl 授权终端，请在终端中完成操作'}
        result = run(command, timeout=120, env=env)
        return {'message': result or '操作已完成'}

    def settings(self, patch):
        # Share clashctl's subscription lock so an update cannot overwrite a UI edit.
        env = dict(os.environ, CLASHCTL_HOME=str(self.home))
        script = '. "$CLASHCTL_HOME/scripts/cmd/clashctl.sh" || exit; _ui_hold() { printf "locked\\n"; read -r _ui_release; }; _with_profiles_lock _ui_hold'
        process = subprocess.Popen(['bash', '-c', script], env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            if process.stdout.readline().strip() != 'locked':
                _out, error = process.communicate(timeout=5)
                raise UIError(ANSI.sub('', error).strip() or '无法取得配置锁')
            self._settings_locked(patch)
        finally:
            if process.poll() is None:
                process.communicate('\n', timeout=5)

    def _settings_locked(self, patch):
        """Validate complete candidates before applying and persisting a live patch."""
        old_cfg = self.request('/configs')
        old_mixin = self.mixin.read_bytes()
        old_runtime = self.runtime.read_bytes()
        paths = []
        try:
            for content in (old_mixin, b''):
                fd, name = tempfile.mkstemp(prefix='.ui-config-', suffix='.yaml', dir=str(self.runtime.parent))
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(content)
                paths.append(Path(name))
            candidate_mixin, candidate_runtime = paths
            # Normalize empty YAML scalars before yq merges them. Otherwise some
            # yq versions turn the template's null prepend/append entries into strings.
            canonical = json.dumps(self.yaml(self.mixin), ensure_ascii=False)
            candidate_mixin.write_text(canonical)
            env = dict(os.environ, CLASHCTL_HOME=str(self.home), UI_PATCH=json.dumps(patch))
            run([str(self.yq), '-i', '. * env(UI_PATCH)', str(candidate_mixin)], env=env)
            run([str(self.yq), '-P', '-i', '.', str(candidate_mixin)])
            script = '. "$CLASHCTL_HOME/scripts/cmd/clashctl.sh" || exit; CLASH_CONFIG_MIXIN="$1"; _build_runtime_config "$CLASH_CONFIG_BASE"'
            merged = run(['bash', '-c', script, 'clashctl-ui', str(candidate_mixin)], env=env)
            candidate_runtime.write_text(merged + '\n')
            run([str(self.home / 'bin/mihomo'), '-t', '-d', str(self.home / 'resources'), '-f', str(candidate_runtime)], timeout=20)
            self.request('/configs', 'PATCH', patch)
            try:
                atomic_write(self.mixin, candidate_mixin.read_bytes())
                atomic_write(self.runtime, candidate_runtime.read_bytes())
            except OSError:
                atomic_write(self.mixin, old_mixin)
                atomic_write(self.runtime, old_runtime)
                self.request('/configs', 'PATCH', {key: old_cfg[key] for key in patch})
                raise UIError('保存失败，已恢复原设置')
        finally:
            for path in paths:
                with contextlib.suppress(FileNotFoundError):
                    path.unlink()

    def logs(self):
        path = self.home / 'data/mihomo.log'
        if not path.exists():
            return {'lines': []}
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 96000))
            lines = stream.read().decode('utf-8', 'replace').splitlines()[-250:]
        return {'lines': [ANSI.sub('', line) for line in lines]}

    def action(self, data):
        action = data.get('action')
        locked = action != 'delay'
        if locked and not self.lock.acquire(blocking=False):
            raise UIError('另一个操作正在进行，请稍候')
        try:
            if action in ('start', 'stop'):
                tun = bool((self.yaml(self.runtime).get('tun') or {}).get('enable'))
                return self.cli([action], terminal=tun)
            if action == 'tun':
                if type(data.get('enabled')) is not bool:
                    raise UIError('TUN 状态无效')
                return self.cli(['tun', 'on' if data['enabled'] else 'off'], terminal=True)
            if action == 'system-proxy':
                if type(data.get('enabled')) is not bool:
                    raise UIError('系统代理状态无效')
                self.set_system_proxy(data['enabled'])
            elif action == 'settings':
                patch = data.get('patch')
                if not isinstance(patch, dict) or not patch or set(patch) - {'mode', 'allow-lan', 'ipv6', 'log-level'}:
                    raise UIError('不支持的设置')
                for key, value in patch.items():
                    if key == 'mode' and value not in ('rule', 'global', 'direct'):
                        raise UIError('无效的出站模式')
                    if key in ('allow-lan', 'ipv6') and type(value) is not bool:
                        raise UIError('无效的开关状态')
                    if key == 'log-level' and value not in ('debug', 'info', 'warning', 'error', 'silent'):
                        raise UIError('无效的日志级别')
                self.settings(patch)
            elif action in ('select', 'delay'):
                name = data.get('name')
                proxies = self.request('/proxies').get('proxies', {})
                if not isinstance(name, str) or name not in proxies:
                    raise UIError('节点不存在')
                path = '/proxies/' + urllib.parse.quote(name, safe='')
                if action == 'select':
                    member = data.get('member')
                    if proxies[name].get('type') != 'Selector' or member not in proxies[name].get('all', []):
                        raise UIError('请选择可切换的组及有效节点')
                    self.request(path, 'PUT', {'name': member})
                else:
                    query = urllib.parse.urlencode({'url': 'http://www.gstatic.com/generate_204', 'timeout': 5000})
                    return self.request(path + '/delay?' + query, timeout=7)
            elif action == 'close-connection':
                connection_id = data.get('id')
                if not isinstance(connection_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{1,80}', connection_id):
                    raise UIError('连接 ID 无效')
                self.request('/connections/' + connection_id, 'DELETE')
            elif action in ('profile-update', 'profile-use', 'profile-add'):
                tun = bool((self.yaml(self.runtime).get('tun') or {}).get('enable'))
                name = data.get('name', '')
                if not isinstance(name, str) or not name.strip() or len(name) > 150 or name.startswith('-') or any(ord(c) < 32 for c in name):
                    raise UIError('请输入有效的订阅名称')
                if action == 'profile-add':
                    url = data.get('url', '')
                    if not isinstance(url, str) or urllib.parse.urlsplit(url).scheme not in ('http', 'https') or len(url) > 8192:
                        raise UIError('请输入 http 或 https 订阅链接')
                    first = not self.profiles()['profiles']
                    args = ['sub', 'add', '--raw', '-n', name]
                    if first:
                        args.append('--use')
                    args.append(url)
                    return self.cli(args, terminal=tun and first)
                if name not in [p['name'] for p in self.profiles()['profiles']]:
                    raise UIError('订阅不存在')
                return self.cli(['sub', 'use' if action == 'profile-use' else 'update', name], terminal=tun)
            elif action == 'flush-dns':
                self.request('/cache/dns/flush', 'POST')
            else:
                if action != 'system-proxy':
                    raise UIError('未知操作')
            return {'message': '设置已更新' if action == 'settings' else '操作已完成'}
        finally:
            if locked:
                self.lock.release()

    def close(self):
        self.stop_event.set()
        self.pool.shutdown(wait=False)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=0, bridge=None):
        self.bridge = bridge or Bridge()
        self.token = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), Handler)
        self.origin = 'http://127.0.0.1:' + str(self.server_port)

    def server_close(self):
        self.bridge.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send(self, value, status=200, mime='application/json; charset=utf-8', cookie=False):
        payload = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', 'clashctl_ui=' + self.server.token + '; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self):
        if self.headers.get('Host') != self.server.origin[7:]:
            return False
        origin = self.headers.get('Origin')
        if origin and origin != self.server.origin:
            return False
        if self.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site'):
            return False
        return True

    def cookie_ok(self):
        from http.cookies import SimpleCookie
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            value = cookie.get('clashctl_ui')
            return value is not None and secrets.compare_digest(value.value, self.server.token)
        except Exception:
            return False

    def do_GET(self):
        if not self.authorized():
            return self.send({'error': '仅允许本机界面访问'}, 403)
        path = urllib.parse.urlsplit(self.path).path
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8'),
                  '/icon.svg': ('icon.svg', 'image/svg+xml')}
        if path in assets:
            name, mime = assets[path]
            return self.send((ROOT / 'web' / name).read_bytes(), mime=mime, cookie=path == '/')
        if not self.cookie_ok():
            return self.send({'error': '请从本地界面打开'}, 403)
        try:
            if path == '/api/bootstrap':
                return self.send({'token': self.server.token})
            if path == '/api/state':
                return self.send(self.server.bridge.snapshot())
            if path == '/api/logs':
                return self.send(self.server.bridge.logs())
            if path == '/api/rules':
                return self.send(self.server.bridge.request('/rules'))
            return self.send({'error': '未找到'}, 404)
        except (UIError, OSError, ValueError) as exc:
            return self.send({'error': str(exc)}, 503)

    def do_POST(self):
        if not self.authorized() or not self.cookie_ok() or not secrets.compare_digest(self.headers.get('X-UI-Token', ''), self.server.token):
            return self.send({'error': '请求验证失败'}, 403)
        if self.path != '/api/action':
            return self.send({'error': '未找到'}, 404)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > 32768:
                return self.send({'error': '请求大小无效'}, 400)
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('请求格式无效')
            self.send(self.server.bridge.action(data))
        except (ValueError, TypeError):
            self.send({'error': '请求格式无效'}, 400)
        except UIError as exc:
            self.send({'error': str(exc)}, 400)
        except OSError:
            self.send({'error': '无法读写本地配置或启动命令，请检查文件权限'}, 500)
        except Exception:
            self.send({'error': '操作失败，请检查 clashctl 日志'}, 500)
