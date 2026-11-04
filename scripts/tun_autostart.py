#!/usr/bin/env python3
"""Optional systemd boot service using clashctl's existing privileged helper."""
import argparse
import os
from pathlib import Path
import pwd
import shutil
import subprocess


def unit_arg(value):
    value = str(value)
    if any(ord(char) < 32 for char in value):
        raise ValueError('服务路径包含控制字符')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def render_unit(home, uid, helper):
    home = Path(home)
    binary, resources, runtime = home / 'bin/mihomo', home / 'resources', home / 'data/runtime.yaml'
    expected = b''.join(str(value).encode() + b'\0' for value in (binary, '-d', resources, '-f', runtime)).hex()
    return '''[Unit]
Description=Clashctl Desktop TUN kernel for UID ''' + str(uid) + '''
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=oneshot
RemainAfterExit=yes
ExecCondition=''' + unit_arg(home / 'bin/yq') + ' -e ".tun.enable == true" ' + unit_arg(runtime) + '''
ExecStart=/bin/bash ''' + unit_arg(helper) + ' privileged-start ' + str(uid) + ' mihomo ' + ' '.join(unit_arg(value) for value in (binary, resources, runtime)) + '''
ExecStop=/bin/bash ''' + unit_arg(helper) + ' privileged-stop ' + str(uid) + ' mihomo ' + expected + '''
Restart=on-failure
RestartSec=10s
TimeoutStartSec=60s
StandardOutput=append:''' + str(home / 'data/mihomo.log').replace('%', '%%') + '''
StandardError=inherit

[Install]
WantedBy=multi-user.target
'''


def main():
    parser = argparse.ArgumentParser(description='安装或禁用当前用户的 TUN 开机服务')
    parser.add_argument('--uid', required=True, type=int)
    parser.add_argument('--clashctl-home', required=True)
    parser.add_argument('--disable', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('需要通过 sudo 运行，以安装系统级服务')
    if args.uid < 1:
        parser.error('请指定普通用户 UID')
    pwd.getpwuid(args.uid)
    home = Path(args.clashctl_home).resolve()
    if not home.is_dir() or home.stat().st_uid != args.uid:
        parser.error('clashctl 目录必须属于指定的普通用户')
    name = 'clashctl-tun-' + str(args.uid) + '.service'
    if args.disable:
        subprocess.run(['systemctl', 'disable', name], check=True)
        print('已禁用 TUN 开机启动，当前内核继续由 clashctl 管理。')
        return
    if (home / '.clashctl-format').read_text().strip() != '1':
        parser.error('请先安装兼容的 clashctl 版本')
    source = home / 'scripts/lib/service-process.sh'
    helper = Path('/usr/local/libexec/clashctl-desktop') / str(args.uid) / 'service-process.sh'
    helper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(source), str(helper))
    helper.chmod(0o755)
    unit = Path('/etc/systemd/system') / name
    unit.write_text(render_unit(home, args.uid, helper))
    unit.chmod(0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemd-analyze', 'verify', str(unit)], check=True)
    subprocess.run(['systemctl', 'enable', '--now', name], check=True)
    print('TUN 开机服务已启用：' + name)
    print('仅在 clashctl 已开启 TUN 时启动；关闭 TUN 后沿用原有普通用户服务。')


if __name__ == '__main__':
    main()
