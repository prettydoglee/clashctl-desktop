#!/usr/bin/env python3
"""GTK desktop shell, with a dependency-free localhost browser mode."""
import argparse
import json
import os
import sys
import threading
from pathlib import Path

from backend import LocalServer, ROOT
from version import VERSION


def desktop_libraries():
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    for api in ('4.1', '4.0'):
        try:
            gi.require_version('WebKit2', api)
            break
        except ValueError:
            continue
    else:
        raise ImportError('缺少 WebKit GTK；请重新运行 bash install.sh，或使用 --serve')
    from gi.repository import Gtk, WebKit2, Gdk, GLib
    return Gtk, WebKit2, Gdk, GLib


def doctor():
    home = Path(os.environ.get('CLASHCTL_HOME', str(Path.home() / '.clashctl')))
    checks = {name: (home / name).is_file() for name in
              ('bin/yq', 'bin/mihomo', 'scripts/cmd/clashctl.sh', 'data/runtime.yaml')}
    print('Clashctl Desktop ' + VERSION)
    print('clashctl: ' + str(home))
    for name, exists in checks.items():
        print(('OK   ' if exists else 'MISS ') + name)
    try:
        _gtk, webkit, _gdk, _glib = desktop_libraries()
        print('OK   WebKit GTK ' + '.'.join(str(fn()) for fn in
              (webkit.get_major_version, webkit.get_minor_version, webkit.get_micro_version)))
    except (ImportError, ValueError):
        print('INFO 桌面组件未安装；浏览器模式仍可使用 --serve')
    return 0 if all(checks.values()) else 1


def desktop(port):
    Gtk, WebKit2, Gdk, GLib = desktop_libraries()

    app = Gtk.Application(application_id='local.clashctl.ui')
    resources = {}

    def startup(_application):
        try:
            server = LocalServer(port)
        except OSError as exc:
            dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
                                       buttons=Gtk.ButtonsType.CLOSE,
                                       text='无法启动 Clashctl 控制台')
            dialog.format_secondary_text(str(exc))
            dialog.run()
            dialog.destroy()
            return
        resources['server'] = server
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def activate(application):
        server = resources.get('server')
        if server is None:
            return
        if application.get_active_window():
            application.get_active_window().present()
            return
        window = Gtk.ApplicationWindow(application=application, title='Clashctl · 代理控制台')
        window.set_default_size(1250, 850)
        window.set_size_request(720, 540)
        window.set_icon_from_file(str(ROOT / 'web/icon.svg'))
        header = Gtk.HeaderBar(title='Clashctl')
        header.set_show_close_button(True)
        header.set_subtitle('本地代理控制台')
        window.set_titlebar(header)
        data_dir = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'clashctl-ui/webkit'
        cache_dir = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'clashctl-ui/webkit'
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        manager = WebKit2.WebsiteDataManager(base_data_directory=str(data_dir),
                                            base_cache_directory=str(cache_dir))
        # The control surface is entirely local, including while its proxy is stopped.
        manager.set_network_proxy_settings(WebKit2.NetworkProxyMode.NO_PROXY, None)
        context = WebKit2.WebContext.new_with_website_data_manager(manager)
        view = WebKit2.WebView.new_with_context(context)
        # Accelerated compositing can load the DOM yet paint a white native window
        # on this ARM/X11 desktop. Offscreen WebKit snapshots do not reveal it.
        view.get_settings().set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        view.get_settings().set_enable_developer_extras(False)
        view.get_settings().set_allow_file_access_from_file_urls(False)
        view.set_background_color(Gdk.RGBA(0.96, 0.96, 0.97, 1))

        stack = Gtk.Stack()
        stack.add_named(view, 'web')
        status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        status.set_halign(Gtk.Align.CENTER)
        status.set_valign(Gtk.Align.CENTER)
        status.set_margin_start(30)
        status.set_margin_end(30)
        spinner = Gtk.Spinner()
        spinner.set_size_request(28, 28)
        spinner.set_halign(Gtk.Align.CENTER)
        message = Gtk.Label(label='正在加载本地控制台…')
        message.set_line_wrap(True)
        message.set_max_width_chars(60)
        message.set_justify(Gtk.Justification.CENTER)
        message.set_name('desktop-load-message')
        actions = Gtk.Box(spacing=12)
        actions.set_halign(Gtk.Align.CENTER)
        retry = Gtk.Button(label='重新加载')
        retry.set_name('desktop-retry')
        browser = Gtk.Button(label='在浏览器中打开')
        for button in (retry, browser):
            button.set_no_show_all(True)
            actions.pack_start(button, False, False, 0)
        status.pack_start(spinner, False, False, 0)
        status.pack_start(message, False, False, 0)
        status.pack_start(actions, False, False, 0)
        stack.add_named(status, 'status')
        stack.set_visible_child_name('status')
        load_state = {'failed': False, 'timer': 0}

        def cancel_watchdog():
            if load_state['timer']:
                GLib.source_remove(load_state['timer'])
                load_state['timer'] = 0

        def show_failure(detail):
            cancel_watchdog()
            load_state['failed'] = True
            spinner.stop()
            spinner.hide()
            message.set_text('控制台界面加载失败\n' + detail)
            retry.show()
            browser.show()
            stack.set_visible_child_name('status')

        def timed_out():
            load_state['timer'] = 0
            show_failure('本地页面暂未响应，请重新加载。')
            return False

        def load_changed(_view, event):
            if event == WebKit2.LoadEvent.STARTED:
                cancel_watchdog()
                load_state['failed'] = False
                message.set_text('正在加载本地控制台…')
                spinner.show()
                spinner.start()
                retry.hide()
                browser.hide()
                stack.set_visible_child_name('status')
                load_state['timer'] = GLib.timeout_add_seconds(12, timed_out)
            elif event == WebKit2.LoadEvent.FINISHED and not load_state['failed']:
                cancel_watchdog()
                spinner.stop()
                stack.set_visible_child_name('web')

        def load_failed(_view, _event, _uri, error):
            if not load_state['failed']:
                show_failure(error.message)
            return True

        def navigation(_view, decision, kind):
            if kind == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
                uri = decision.get_navigation_action().get_request().get_uri()
                if uri and not uri.startswith(server.origin + '/'):
                    decision.ignore()
                    return True
            elif kind == WebKit2.PolicyDecisionType.RESPONSE:
                status_code = decision.get_response().get_status_code()
                if status_code >= 400:
                    decision.ignore()
                    show_failure('本地服务返回 HTTP ' + str(status_code))
                    return True
            return False

        view.connect('decide-policy', navigation)
        view.connect('load-changed', load_changed)
        view.connect('load-failed', load_failed)
        view.connect('web-process-terminated', lambda _view, reason: show_failure('网页渲染进程已退出：' + reason.value_nick))
        retry.connect('clicked', lambda _button: view.load_uri(server.origin + '/'))
        browser.connect('clicked', lambda _button: Gtk.show_uri_on_window(window, server.origin + '/', Gdk.CURRENT_TIME))
        window.connect('destroy', lambda _window: cancel_watchdog())
        window.add(stack)
        view.load_uri(server.origin + '/')
        window.show_all()

    app.connect('startup', startup)
    app.connect('activate', activate)
    try:
        return app.run([])
    finally:
        server = resources.get('server')
        if server:
            server.shutdown()
            server.server_close()


def main():
    metadata = ROOT / 'install.json'
    if metadata.is_file() and not os.environ.get('CLASHCTL_HOME'):
        os.environ['CLASHCTL_HOME'] = json.loads(metadata.read_text())['clashctl_home']
    parser = argparse.ArgumentParser(description='FlClash 风格的 clashctl 本地桌面控制台')
    parser.add_argument('--version', action='version', version='Clashctl Desktop ' + VERSION)
    parser.add_argument('--doctor', action='store_true', help='检查依赖与安装路径，不显示密钥')
    parser.add_argument('--serve', action='store_true', help='仅运行本地网页服务')
    parser.add_argument('--port', type=int, default=17890, help='本机端口，默认 17890；0 表示随机')
    args = parser.parse_args()
    if args.doctor:
        return doctor()
    if args.serve:
        try:
            server = LocalServer(args.port)
        except OSError as exc:
            print('无法启动控制台：' + str(exc), file=sys.stderr)
            return 1
        print('Clashctl UI: ' + server.origin, flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    try:
        return desktop(args.port)
    except (ImportError, ValueError) as exc:
        print('桌面组件不可用：' + str(exc) + '\n可使用 --serve 在浏览器中打开。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
