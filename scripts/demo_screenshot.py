#!/usr/bin/env python3
"""Generate the README screenshot from fictional data, never the live proxy."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import desktop_libraries

Gtk, WebKit2, _Gdk, GLib = desktop_libraries()
server = subprocess.Popen([sys.executable, str(ROOT / 'tests/demo_server.py')], stdout=subprocess.PIPE, text=True)
origin = server.stdout.readline().strip()
window = Gtk.Window(title='Clashctl Desktop · Fictional demo')
window.set_default_size(1250, 1020)
view = WebKit2.WebView.new_with_context(WebKit2.WebContext.new_ephemeral())
view.get_settings().set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
window.add(view)
window.show_all()
success = []


def capture():
    def ready(widget, result, _data):
        value = widget.run_javascript_finish(result).get_js_value().to_boolean()
        if not value:
            print('Screenshot refused: fictional data did not load', file=sys.stderr)
            Gtk.main_quit()
            return

        def saved(widget, result, _data):
            (ROOT / 'docs').mkdir(exist_ok=True)
            widget.get_snapshot_finish(result).write_to_png(str(ROOT / 'docs/screenshot.png'))
            success.append(True)
            Gtk.main_quit()

        view.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, saved, None)

    view.run_javascript('theme("light");navigate("dashboard");document.body.innerText.includes("示例订阅") && state.directory.includes("演示数据")', None, ready, None)
    return False


try:
    view.load_uri(origin + '/')
    GLib.timeout_add(3500, capture)
    GLib.timeout_add(15000, lambda: (Gtk.main_quit(), False)[1])
    Gtk.main()
finally:
    window.destroy()
    server.terminate()
    server.wait(timeout=10)
if not success:
    sys.exit(1)
print('Public screenshot saved using fictional data only')
