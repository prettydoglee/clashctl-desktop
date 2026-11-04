"""Fictional, localhost-only data for public screenshots and interface checks."""
import argparse
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import LocalServer

MB, GB = 1024 ** 2, 1024 ** 3


class DemoBridge:
    def snapshot(self):
        leaf_names = ['日本 · 示例 01', '新加坡 · 示例 02', '香港 · 示例 03', '美国 · 示例 04']
        proxies = {name: {'name': name, 'type': 'Shadowsocks', 'udp': True, 'history': [{'delay': delay}]}
                   for name, delay in zip(leaf_names, [38, 64, 22, 126])}
        for name, kind, current in [('节点选择', 'Selector', leaf_names[0]), ('自动选择', 'URLTest', leaf_names[2]), ('故障转移', 'Fallback', leaf_names[1])]:
            proxies[name] = {'name': name, 'type': kind, 'now': current, 'all': leaf_names, 'history': []}
        connections = [{'id': 'demo-' + str(index), 'metadata': {'host': host, 'network': 'tcp', 'process': '示例应用', 'destinationPort': '443', 'sourceIP': '192.0.2.10'},
                        'chains': [leaf_names[index % 4], '节点选择'], 'rule': 'DomainSuffix', 'rulePayload': 'example',
                        'upload': (index + 1) * 32 * 1024, 'download': (5 - index) * 4 * MB}
                       for index, host in enumerate(['docs.example', 'code.example', 'media.example', 'mail.example', 'status.example'])]
        return {'online': True, 'error': '', 'version': 'v1.19.x · 演示',
                'config': {'mode': 'rule', 'mixed-port': 7890, 'socks-port': 7891, 'allow-lan': False, 'ipv6': False, 'log-level': 'info', 'tun': {'enable': False}},
                'traffic': {'down': 3.2 * MB, 'up': 128 * 1024},
                'samples': [{'down': (1.7 + math.sin(i / 5) + .4 * math.sin(i / 2)) * MB,
                             'up': (90 + 35 * math.cos(i / 6)) * 1024, 'time': time.time() - 60 + i} for i in range(60)],
                'connections': connections, 'uploadTotal': 1.2 * GB, 'downloadTotal': 8.6 * GB,
                'memory': 88 * MB, 'proxies': proxies,
                'subscriptions': {'current': '示例订阅', 'profiles': [{'name': '示例订阅', 'host': 'subscription.example',
                    'updated': '演示数据', 'usage': {'upload': 2 * GB, 'download': 40 * GB, 'total': 100 * GB}, 'active': True}]},
                'systemProxy': {'available': True, 'enabled': False, 'mode': 'none'}, 'directory': '~/.clashctl · 演示数据'}

    def request(self, path):
        if path == '/rules':
            return {'rules': [{'type': 'DomainSuffix', 'payload': 'example', 'proxy': '节点选择'},
                              {'type': 'IP-CIDR', 'payload': '192.0.2.0/24', 'proxy': 'DIRECT'},
                              {'type': 'Match', 'payload': '', 'proxy': '节点选择'}]}
        return {}

    def logs(self):
        return {'lines': ['[演示数据] level=info msg="Mihomo is running"', '[演示数据] level=info msg="Profile loaded"']}

    def action(self, _data):
        return {'message': '演示环境不执行实际操作'}

    def close(self):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = LocalServer(args.port, DemoBridge())
    print(server.origin, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
