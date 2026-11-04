import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('installer', ROOT / 'scripts/install_app.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ApplicationInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.prefix = self.home / '.local/share/clashctl-desktop'
        self.bin_dir = self.home / '.local/bin'
        self.core = self.home / '.clashctl'
        self.environment = patch.dict(os.environ, {'HOME': str(self.home),
            'XDG_DATA_HOME': str(self.home / '.local/share'),
            'XDG_CONFIG_HOME': str(self.home / '.config')})
        self.environment.start()
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)
        self.environment.stop()
        self.temp.cleanup()

    def install(self):
        installer.install(self.prefix, self.bin_dir, self.core, web=True)

    def test_install_from_allowlist_excludes_credentials_and_captures(self):
        source = self.base / 'source'
        for name in installer.FILES:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(ROOT / name), str(target))
        (source / '.env').write_text('PRIVATE_SUBSCRIPTION=do-not-copy\n')
        (source / 'preview.png').write_bytes(b'private screenshot')
        (source / 'data').mkdir()
        (source / 'data/runtime.yaml').write_text('secret: private-controller-token\n')
        with patch.object(installer, 'SOURCE', source):
            self.install()
        self.assertFalse((self.prefix / '.env').exists())
        self.assertFalse((self.prefix / 'preview.png').exists())
        self.assertFalse((self.prefix / 'data').exists())
        self.assertTrue((self.bin_dir / 'clashctl-ui').is_file())

    def test_launch_from_path_with_shell_metacharacters(self):
        self.prefix = self.home / 'app with spaces $value `literal`'
        self.install()
        result = subprocess.run([str(self.bin_dir / 'clashctl-ui'), '--version'], capture_output=True, text=True, check=True)
        self.assertIn('Clashctl Desktop 0.1.0', result.stdout)
        self.assertFalse((self.home / 'literal').exists())

    def test_repeat_install_keeps_shell_and_core_configuration(self):
        bashrc = self.home / '.bashrc'
        bashrc.write_text('# existing ROS configuration\n')
        self.core.mkdir()
        secret = self.core / 'config.yaml'
        secret.write_text('personal configuration\n')
        self.install()
        self.install()
        self.assertEqual(bashrc.read_text().count('# >>> clashctl-desktop PATH >>>'), 1)
        self.assertTrue(bashrc.read_text().startswith('# existing ROS configuration'))
        self.assertEqual(secret.read_text(), 'personal configuration\n')

    def test_uninstall_preserves_runtime_and_unmanaged_files(self):
        self.core.mkdir()
        keep = self.core / 'personal.yaml'
        keep.write_text('do not delete')
        self.install()
        retained = self.prefix / 'personal-note.txt'
        retained.write_text('retain me')
        metadata = self.prefix / 'install.json'
        data = json.loads(metadata.read_text())
        data['files'].append('../../.clashctl/personal.yaml')
        metadata.write_text(json.dumps(data))
        installer.uninstall(self.prefix)
        self.assertEqual(keep.read_text(), 'do not delete')
        self.assertEqual(retained.read_text(), 'retain me')
        self.assertFalse((self.bin_dir / 'clashctl-ui').exists())

    def test_refuses_to_overwrite_an_unrelated_command(self):
        self.bin_dir.mkdir(parents=True)
        command = self.bin_dir / 'clashctl-ui'
        command.write_text('# unrelated application\n')
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(command.read_text(), '# unrelated application\n')
        self.assertFalse(self.prefix.exists())

    def test_install_sh_help_and_missing_dependency_fail_cleanly(self):
        help_result = subprocess.run(['bash', str(ROOT / 'install.sh'), '--help'], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0)
        result = subprocess.run(['bash', str(ROOT / 'install.sh'), '--web', '--skip-deps', '--skip-clashctl', '--no-launch', '--clashctl-home', str(self.core)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('没有完整的', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
