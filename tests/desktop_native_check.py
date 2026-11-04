"""Check the actual desktop window pixels, rather than a WebKit offscreen snapshot.

Run with the desktop app closed. Reads live proxy state; changes no proxy settings.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app
Gtk, WebKit2, Gdk, GLib = app.desktop_libraries()

destination = Path(__file__).resolve().parent.parent / 'preview-native.png'
original = WebKit2.WebView.new_with_context
checks = []
created = []


def instrument(context):
    view = original(context)
    created.append(view)

    def check():
        application = Gtk.Application.get_default()
        window = application.get_windows()[0]
        window.present()
        width, height = window.get_size()
        pixels = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, width, height)
        pixels.savev(str(destination), 'png', [], [])
        raw = pixels.get_pixels()
        stride, channels = pixels.get_rowstride(), pixels.get_n_channels()
        # Exclude the window decorations. A loaded DOM in a white native window
        # has one body color; the real dashboard contains text, cards and controls.
        colors = set()
        for y in range(110, height - 30, 7):
            for x in range(45, width - 30, 7):
                offset = y * stride + x * channels
                colors.add(bytes(raw[offset:offset + 3]))
        painted = len(colors) > 100
        checks.append(painted)
        print('Native window:', width, height, 'body colors:', len(colors), 'painted:', painted, flush=True)

        def done(widget, result, _data):
            try:
                data = json.loads(widget.run_javascript_finish(result).get_js_value().to_string())
                print('DOM:', json.dumps(data, ensure_ascii=False), flush=True)
                checks.append(data.get('ready') is True and data.get('online') is True)
                policy = widget.get_settings().get_hardware_acceleration_policy()
                checks.append(policy == WebKit2.HardwareAccelerationPolicy.NEVER)
                print('Hardware acceleration:', policy.value_nick, flush=True)
            except Exception as exc:
                checks.append(False)
                print('FAILED:', str(exc), flush=True)
            # Exercise a real HTTP failure in the production shell, then retry.
            origin = widget.get_uri().split('#', 1)[0].rstrip('/')
            widget.load_uri(origin + '/missing-native-check')
            GLib.timeout_add(1200, check_failure)

        script = 'JSON.stringify({ready:!!document.getElementById("dashboard"),online:typeof state!=="undefined"&&state?state.online:false})'
        view.run_javascript(script, None, done, None)
        return False

    GLib.timeout_add(6500, check)
    return view


def find_named(widget, name):
    if widget.get_name() == name:
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = find_named(child, name)
            if found:
                return found
    return None


def check_failure():
    window = Gtk.Application.get_default().get_windows()[0]
    message = find_named(window, 'desktop-load-message')
    retry = find_named(window, 'desktop-retry')
    visible = bool(message and message.get_mapped() and 'HTTP 404' in message.get_text())
    checks.append(visible)
    print('Native HTTP error visible:', visible,
          'message:', message.get_text() if message else 'missing', flush=True)
    if not retry:
        checks.append(False)
        Gtk.Application.get_default().quit()
    else:
        retry.clicked()
        GLib.timeout_add(1800, check_retry)
    return False


def check_retry():
    view = created[0]
    window = Gtk.Application.get_default().get_windows()[0]
    stack = window.get_child()
    restored = stack.get_visible_child_name() == 'web' and view.get_title() == 'Clashctl · 本地代理控制台'
    checks.append(restored)
    print('Native retry restored dashboard:', restored, flush=True)
    Gtk.Application.get_default().quit()
    return False


def timeout():
    checks.append(False)
    print('FAILED: native window check timed out', flush=True)
    Gtk.Application.get_default().quit()
    return False


WebKit2.WebView.new_with_context = instrument
GLib.timeout_add(20000, timeout)
app.desktop(17890)
if not created:
    print('FAILED: close the existing Clashctl window before running this check', flush=True)
    sys.exit(1)
if not checks or not all(checks):
    sys.exit(1)
print('Native desktop rendering check passed:', destination, flush=True)
