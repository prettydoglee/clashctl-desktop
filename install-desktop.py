#!/usr/bin/env python3
"""Install launchers for this checkout in the current user's desktop session."""
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent
data_home = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
applications = data_home / 'applications'
applications.mkdir(parents=True, exist_ok=True)
entry = applications / 'local.clashctl.ui.desktop'
executable = str(root / 'launch.sh').replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
entry.write_text('[Desktop Entry]\n'
                 'Type=Application\n'
                 'Name=Clashctl\n'
                 'Name[zh_CN]=Clashctl 代理控制台\n'
                 'Comment=FlClash 风格的本地 clashctl 控制界面\n'
                 'Exec="' + executable + '"\n'
                 'Icon=' + str(root / 'web/icon.svg') + '\n'
                 'Terminal=false\n'
                 'Categories=Network;\n'
                 'StartupNotify=true\n'
                 'StartupWMClass=local.clashctl.ui\n', encoding='utf-8')
entry.chmod(0o755)
shortcut = None
try:
    value = subprocess.check_output(['xdg-user-dir', 'DESKTOP'], text=True).strip()
    desktop = Path(value) if value else None
except (OSError, subprocess.CalledProcessError):
    desktop = Path.home() / 'Desktop'
if desktop is not None and desktop != Path.home():
    desktop.mkdir(parents=True, exist_ok=True)
    shortcut = desktop / 'Clashctl.desktop'
    shutil.copy2(str(entry), str(shortcut))
    if shutil.which('gio'):
        subprocess.run(['gio', 'set', str(shortcut), 'metadata::trusted', 'true'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if shutil.which('update-desktop-database'):
    subprocess.run(['update-desktop-database', str(applications)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print('应用菜单：' + str(entry))
if shortcut:
    print('桌面入口：' + str(shortcut))
