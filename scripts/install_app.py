#!/usr/bin/env python3
"""Install only allow-listed application sources; never copy runtime credentials."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent.parent
FILES = ('app.py', 'backend.py', 'version.py', 'launch.sh', 'clashctl-bridge.sh',
         'install-desktop.py', 'uninstall.sh', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
         'README.md', 'scripts/install_app.py', 'scripts/tun_autostart.py',
         'web/index.html', 'web/app.js', 'web/style.css', 'web/icon.svg', 'docs/screenshot.png')


def atomic(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.install-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content if isinstance(content, bytes) else content.encode())
        os.chmod(temporary, mode)
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(prefix, bin_dir, core_home, web=False):
    prefix, bin_dir, core_home = (Path(path).expanduser().resolve() for path in (prefix, bin_dir, core_home))
    if prefix in (SOURCE, Path('/'), Path.home()):
        raise ValueError('安装目录必须与源码目录分开')
    if any(ord(char) < 32 for path in (prefix, bin_dir, core_home) for char in str(path)):
        raise ValueError('安装路径不能包含控制字符')
    if prefix.exists() and any(prefix.iterdir()) and not (prefix / 'install.json').is_file():
        raise ValueError('目标目录已有其他文件，请换一个 --prefix')
    for name in FILES:
        if not (SOURCE / name).is_file():
            raise ValueError('源码不完整：' + name)
    command = bin_dir / 'clashctl-ui'
    if command.exists() and 'clashctl-desktop' not in command.read_text() and str(prefix) not in command.read_text():
        raise ValueError('命令路径已被其他程序占用：' + str(command))
    for name in FILES:
        src = SOURCE / name
        mode = 0o755 if name.endswith('.sh') else 0o644
        atomic(prefix / name, src.read_bytes(), mode)
    metadata = {'application': 'clashctl-desktop', 'prefix': str(prefix), 'bin_dir': str(bin_dir),
                'clashctl_home': str(core_home), 'files': list(FILES), 'web': web}
    atomic(prefix / 'install.json', json.dumps(metadata, indent=2) + '\n', 0o600)
    launcher = '#!/usr/bin/env bash\nexport CLASHCTL_HOME=' + shlex.quote(str(core_home)) + '\nexec ' + shlex.quote(str(prefix / 'launch.sh')) + ' "$@"\n'
    atomic(command, launcher, 0o755)
    if not web:
        subprocess.run([sys.executable, str(prefix / 'install-desktop.py')], check=True)
    # Idempotent PATH integration for Bash and Zsh; no changes to ROS or Conda.
    if bin_dir == Path.home() / '.local/bin':
        block = '\n# >>> clashctl-desktop PATH >>>\ncase ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac\n# <<< clashctl-desktop PATH <<<\n'
        for name in ('.profile', '.bashrc', '.zshrc'):
            path = Path.home() / name
            if name == '.zshrc' and not path.exists():
                continue
            content = path.read_text() if path.exists() else ''
            if '# >>> clashctl-desktop PATH >>>' not in content:
                mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
                atomic(path, content + block, mode)
    print('已安装控制台：' + str(prefix))
    print('命令入口：' + str(command))


def uninstall(prefix):
    prefix = Path(prefix).expanduser().resolve()
    marker = prefix / 'install.json'
    metadata = json.loads(marker.read_text())
    if metadata.get('application') != 'clashctl-desktop' or metadata.get('prefix') != str(prefix):
        raise ValueError('不是本安装器管理的目录')
    command = Path(metadata['bin_dir']) / 'clashctl-ui'
    if command.is_file() and str(prefix / 'launch.sh') in command.read_text():
        command.unlink()
    data_home = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    entries = [data_home / 'applications/local.clashctl.ui.desktop']
    try:
        desktop = subprocess.check_output(['xdg-user-dir', 'DESKTOP'], text=True).strip()
        if desktop and Path(desktop) != Path.home():
            entries.append(Path(desktop) / 'Clashctl.desktop')
    except (OSError, subprocess.CalledProcessError):
        pass
    for entry in entries:
        if entry.is_file() and str(prefix / 'launch.sh') in entry.read_text():
            entry.unlink()
    for name in FILES:
        path = prefix / name
        if path.is_file() or path.is_symlink():
            path.unlink()
    marker.unlink()
    for path in (prefix / '__pycache__', prefix / 'scripts/__pycache__'):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(str(path))
    for name in ('scripts', 'web', 'docs'):
        path = prefix / name
        if path.exists() and not any(path.iterdir()):
            path.rmdir()
    if not any(prefix.iterdir()):
        prefix.rmdir()
    print('控制台已卸载。clashctl、订阅、内核和用户偏好均保留。')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', default=str(Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'clashctl-desktop'))
    parser.add_argument('--bin-dir', default=str(Path.home() / '.local/bin'))
    parser.add_argument('--clashctl-home', default=str(Path.home() / '.clashctl'))
    parser.add_argument('--web', action='store_true')
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    if args.uninstall:
        uninstall(args.prefix)
    else:
        install(args.prefix, args.bin_dir, args.clashctl_home, args.web)


if __name__ == '__main__':
    main()
