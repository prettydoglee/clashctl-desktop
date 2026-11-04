import http.client
import collections
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import Bridge, LocalServer, UIError, atomic_write, find_yq


class ParserDiscoveryTests(unittest.TestCase):
    def test_reuses_system_mikefarah_yq_v4(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('backend.shutil.which', return_value='/usr/local/bin/yq'), patch('backend.run', return_value='yq (https://github.com/mikefarah/yq/) version v4.50.1'):
                self.assertEqual(find_yq(Path(directory)), Path('/usr/local/bin/yq'))

    def test_rejects_incompatible_python_yq(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('backend.shutil.which', return_value='/usr/bin/yq'), patch('backend.run', return_value='yq 3.4.3'):
                self.assertEqual(find_yq(Path(directory)), Path(directory) / 'bin/yq')


class HTTPAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = Mock()
        cls.bridge.snapshot.return_value = {'online': True, 'config': {'mode': 'rule'}}
        cls.bridge.logs.return_value = {'lines': []}
        cls.bridge.action.return_value = {'message': 'ok'}
        cls.server = LocalServer(0, cls.bridge)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, method='GET', headers=None, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        connection.close()
        return result

    def auth(self):
        return {'Cookie': 'clashctl_ui=' + self.server.token,
                'X-UI-Token': self.server.token, 'Content-Type': 'application/json'}

    def test_controller_data_requires_session(self):
        self.assertEqual(self.request('/api/state')[0], 403)
        self.assertEqual(self.request('/api/state', headers=self.auth())[0], 200)

    def test_root_sets_private_cookie_and_frame_protection(self):
        code, headers, _body = self.request('/')
        self.assertEqual(code, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_cross_origin_and_dns_rebinding_are_denied(self):
        headers = dict(self.auth(), Origin='https://external.example')
        self.assertEqual(self.request('/api/state', headers=headers)[0], 403)
        self.assertEqual(self.request('/', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.request('/', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_mutations_require_both_session_and_csrf_token(self):
        headers = {'Cookie': 'clashctl_ui=' + self.server.token}
        self.assertEqual(self.request('/api/action', 'POST', headers, '{}')[0], 403)
        headers = self.auth()
        self.assertEqual(self.request('/api/action', 'POST', headers, '{"action":"test"}')[0], 200)

    def test_invalid_json_and_unknown_routes(self):
        self.assertEqual(self.request('/api/action', 'POST', self.auth(), '[]')[0], 400)
        self.assertEqual(self.request('/api/action', 'POST', self.auth(), '{broken')[0], 400)
        self.assertEqual(self.request('/../../backend.py', headers=self.auth())[0], 404)
        self.assertEqual(self.request('/api/anything', 'POST', self.auth(), '{}')[0], 404)


class ConfigurationTests(unittest.TestCase):
    """Use the installed parser, merge logic, and kernel validator in an isolated home."""
    def setUp(self):
        installed = Path(os.environ.get('CLASHCTL_TEST_HOME', str(Path.home() / '.clashctl')))
        parser = find_yq(installed)
        if not parser.exists() or not (installed / 'bin/mihomo').exists():
            self.skipTest('Requires the local clashctl installation')
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        (self.home / 'data').mkdir()
        (self.home / 'bin').mkdir()
        (self.home / 'resources').mkdir()
        (self.home / 'scripts').symlink_to(installed / 'scripts')
        (self.home / 'bin/yq').symlink_to(parser)
        (self.home / 'bin/mihomo').symlink_to(installed / 'bin/mihomo')
        (self.home / '.clashctl-format').write_text('1\n')
        (self.home / '.env').write_text('CLASHCTL_KERNEL=mihomo\n')
        self.base = ('mixed-port: 17899\nexternal-controller: 127.0.0.1:0\n'
                     'secret: fixture-only-secret\nmode: rule\nallow-lan: false\n'
                     'dns:\n  enable: false\n'
                     'proxy-groups:\n  - name: 测试组\n    type: select\n    proxies: [DIRECT]\n'
                     'rules: [MATCH,DIRECT]\n')
        # A single MATCH rule is one YAML scalar, not two list entries.
        self.base = self.base.replace('rules: [MATCH,DIRECT]', 'rules: ["MATCH,DIRECT"]')
        (self.home / 'data/config.yaml').write_text(self.base)
        (self.home / 'data/runtime.yaml').write_text(self.base)
        (self.home / 'data/mixin.yaml').write_text('mode: rule\nallow-lan: false\n_custom:\n  retained: true\n')
        self.bridge = Bridge.__new__(Bridge)
        self.bridge.home = self.home
        self.bridge.yq = self.home / 'bin/yq'
        self.bridge.runtime = self.home / 'data/runtime.yaml'
        self.bridge.mixin = self.home / 'data/mixin.yaml'
        self.bridge.request = Mock(return_value={'mode': 'rule', 'allow-lan': False})
        self.bridge.lock = threading.Lock()
        self.bridge.cache_lock = threading.Lock()
        self.bridge.yaml_cache = {}

    def tearDown(self):
        if hasattr(self, 'temp'):
            self.temp.cleanup()

    def test_mode_persists_and_retains_clashctl_overrides(self):
        self.bridge.settings({'mode': 'direct'})
        self.assertEqual(self.bridge.yaml(self.bridge.mixin)['mode'], 'direct')
        self.assertEqual(self.bridge.yaml(self.bridge.runtime)['mode'], 'direct')
        self.assertTrue(self.bridge.yaml(self.bridge.mixin)['_custom']['retained'])
        self.assertNotIn('_custom', self.bridge.yaml(self.bridge.runtime))
        self.assertEqual(self.bridge.runtime.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.home / 'data/profiles.lock.d').exists())
        self.bridge.request.assert_any_call('/configs', 'PATCH', {'mode': 'direct'})

    def test_settings_accept_upstream_template_empty_overrides(self):
        with self.bridge.mixin.open('a') as stream:
            stream.write('proxies:\n  prepend:\n  append:\nproxy-groups:\n  prepend:\n  append:\nrules:\n  prepend:\n  append:\n')
        self.bridge.settings({'mode': 'global'})
        runtime = self.bridge.yaml(self.bridge.runtime)
        self.assertEqual(runtime['mode'], 'global')
        self.assertEqual(runtime['rules'], ['MATCH,DIRECT'])
        self.assertIsNone(self.bridge.yaml(self.bridge.mixin)['proxies']['prepend'])

    def test_first_subscription_is_enabled_after_import(self):
        self.bridge.profiles = Mock(return_value={'profiles': []})
        self.bridge.yaml = Mock(return_value={'tun': {'enable': False}})
        self.bridge.cli = Mock(return_value={'message': 'ok'})
        self.bridge.action({'action': 'profile-add', 'name': 'example', 'url': 'https://subscription.example/config'})
        self.bridge.cli.assert_called_once_with(['sub', 'add', '--raw', '-n', 'example', '--use', 'https://subscription.example/config'], terminal=False)

    def test_failed_live_update_preserves_both_files(self):
        before = [path.read_bytes() for path in (self.bridge.mixin, self.bridge.runtime)]
        def request(_path, method='GET', _data=None):
            if method == 'PATCH':
                raise UIError('simulated controller failure')
            return {'mode': 'rule'}
        self.bridge.request.side_effect = request
        with self.assertRaises(UIError):
            self.bridge.settings({'mode': 'direct'})
        self.assertEqual(before, [path.read_bytes() for path in (self.bridge.mixin, self.bridge.runtime)])
        self.assertFalse((self.home / 'data/profiles.lock.d').exists())

    def test_disk_failure_restores_live_and_saved_settings(self):
        before = [path.read_bytes() for path in (self.bridge.mixin, self.bridge.runtime)]
        calls = []
        def write(path, data):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('simulated disk failure')
            return atomic_write(path, data)
        with patch('backend.atomic_write', side_effect=write), self.assertRaises(UIError):
            self.bridge.settings({'mode': 'direct'})
        self.assertEqual(before, [path.read_bytes() for path in (self.bridge.mixin, self.bridge.runtime)])
        self.bridge.request.assert_any_call('/configs', 'PATCH', {'mode': 'rule'})

    def test_api_rejects_arbitrary_settings_and_shell_actions(self):
        with self.assertRaises(UIError):
            self.bridge.action({'action': 'settings', 'patch': {'external-controller': '0.0.0.0:9999'}})
        with self.assertRaises(UIError):
            self.bridge.action({'action': 'settings', 'patch': {'mode': 'invalid'}})
        with self.assertRaises(UIError):
            self.bridge.action({'action': 'exec', 'command': 'anything'})

    def test_snapshot_keeps_secrets_on_server(self):
        (self.home / 'data/profiles.yaml').write_text('use: example\nprofiles:\n  - name: example\n    url: https://subscription.example/private-token\n')
        self.bridge.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.addCleanup(self.bridge.pool.shutdown)
        self.bridge.traffic = {'up': 0, 'down': 0}
        self.bridge.traffic_at = 0
        self.bridge.samples = collections.deque()
        self.bridge.system_proxy = Mock(return_value={'available': False, 'enabled': False})
        self.bridge.request.side_effect = lambda path: {
            '/version': {'version': 'test'},
            '/configs': {'mode': 'rule', 'secret': 'controller-private-secret'},
            '/connections': {'connections': []},
            '/proxies': {'proxies': {}},
        }[path]
        result = self.bridge.snapshot()
        payload = json.dumps(result)
        self.assertNotIn('controller-private-secret', payload)
        self.assertNotIn('private-token', payload)
        self.assertEqual(result['subscriptions']['profiles'][0]['host'], 'subscription.example')

    def test_node_names_are_encoded_and_membership_checked(self):
        self.bridge.request.return_value = {'proxies': {'组 / A': {'type': 'Selector', 'all': ['节点 B']}}}
        with self.assertRaises(UIError):
            self.bridge.action({'action': 'select', 'name': '组 / A', 'member': 'other'})
        self.bridge.action({'action': 'select', 'name': '组 / A', 'member': '节点 B'})
        self.bridge.request.assert_any_call('/proxies/%E7%BB%84%20%2F%20A', 'PUT', {'name': '节点 B'})

    def test_system_proxy_restores_original_desktop_configuration(self):
        self.bridge.state_dir = self.home / 'state'
        self.bridge.system_proxy = Mock(return_value={'available': True, 'enabled': False})
        original = {
            ('org.gnome.system.proxy', 'mode'): "'auto'",
            **{('org.gnome.system.proxy.' + scheme, key): value
               for scheme in ('http', 'https', 'socks')
               for key, value in [('host', "'previous.proxy'"), ('port', '8080')]},
        }
        desktop = dict(original)
        def gsettings(args, **_kwargs):
            _command, verb, schema, key, *values = args
            if verb == 'get':
                return desktop[(schema, key)]
            desktop[(schema, key)] = values[0]
            return ''
        with patch('backend.run', side_effect=gsettings):
            # Avoid parsing YAML through the mocked subprocess runner.
            self.bridge.yaml = Mock(return_value={'mixed-port': 17899, 'socks-port': 17900})
            self.bridge.set_system_proxy(True)
            self.assertEqual(desktop[('org.gnome.system.proxy', 'mode')], "'manual'")
            self.assertEqual(desktop[('org.gnome.system.proxy.http', 'port')], '17899')
            self.bridge.set_system_proxy(False)
        self.assertEqual(desktop, original)
        self.assertFalse((self.bridge.state_dir / 'proxy-backup.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
