"""Exercise a fresh installed copy with a local, nonfunctional subscription fixture.

The test requires an isolated HOME different from the current user's home and
refuses a console that already has subscriptions. No public proxy is contacted.
"""
import argparse
import http.cookiejar
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import urllib.request


class Subscription(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'''mode: rule
proxies:
  - name: Example Only
    type: ss
    server: 127.0.0.1
    port: 9
    cipher: aes-128-gcm
    password: fixture-not-a-service
proxy-groups:
  - name: Example
    type: select
    proxies: [DIRECT, Example Only]
rules: ["MATCH,DIRECT"]
'''
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main(home):
    home = Path(home).resolve()
    if home == Path.home().resolve():
        raise ValueError('请传入独立测试 HOME，不能使用当前用户目录')
    marker = Path('/run/clashctl') / (str(os.getuid()) + '.mihomo.process')
    if marker.exists() and re.search(r'(?<![\w/.-])/run/clashctl', (home / '.clashctl/scripts/lib/service.sh').read_text()):
        raise ValueError('宿主机正在运行 TUN，请隔离测试依赖的特权进程命名空间')
    env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / '.local/share'),
               XDG_CONFIG_HOME=str(home / '.config'), XDG_CACHE_HOME=str(home / '.cache'),
               XDG_STATE_HOME=str(home / '.local/state'), CLASHCTL_HOME=str(home / '.clashctl'), CI='1')
    cli_script = 'source "$CLASHCTL_HOME/scripts/cmd/clashctl.sh"; clashctl "$1"'
    subprocess.run(['bash', '-c', cli_script, 'smoke', 'start'], env=env, check=True, stdout=subprocess.DEVNULL)
    fixture = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Subscription)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    process = subprocess.Popen([str(home / '.local/bin/clashctl-ui'), '--serve', '--port', '0'],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        line = process.stdout.readline().strip()
        if not line.startswith('Clashctl UI: http://127.0.0.1:'):
            raise RuntimeError('Installed console did not start: ' + process.stderr.read()[-1000:])
        base = line.split('Clashctl UI: ', 1)[1]
        cookies = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies))

        def get(path):
            with opener.open(base + path, timeout=20) as response:
                return json.load(response)

        with opener.open(base + '/', timeout=10) as response:
            assert response.status == 200
        token = get('/api/bootstrap')['token']
        before = get('/api/state')
        assert before['online'] and not before['subscriptions']['profiles'], 'Test core must be running with no profiles'
        print('Fresh console and empty-profile state: OK', flush=True)

        def action(data):
            request = urllib.request.Request(base + '/api/action', data=json.dumps(data).encode(),
                headers={'Content-Type': 'application/json', 'X-UI-Token': token})
            with opener.open(request, timeout=120) as response:
                return json.load(response)

        action({'action': 'profile-add', 'name': 'Fixture example',
                'url': 'http://127.0.0.1:' + str(fixture.server_port) + '/subscription.yaml'})
        state = get('/api/state')
        assert state['subscriptions']['current'] == 'Fixture example'
        print('First subscription import and automatic activation: OK', flush=True)
        action({'action': 'settings', 'patch': {'mode': 'direct'}})
        assert get('/api/state')['config']['mode'] == 'direct'
        persisted = subprocess.check_output([str(home / '.clashctl/bin/yq'), '.mode',
                                            str(home / '.clashctl/data/mixin.yaml')], text=True).strip()
        assert persisted == 'direct'
        print('Real controller settings and persistence: OK', flush=True)
    finally:
        process.terminate()
        process.wait(timeout=15)
        fixture.shutdown()
        fixture.server_close()
        subprocess.run(['bash', '-c', cli_script, 'smoke', 'stop'], env=env, check=True, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', required=True)
    args = parser.parse_args()
    main(args.home)
