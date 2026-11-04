"""Exercise the real WebKit UI against a running, read-only localhost session."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import desktop_libraries
Gtk, WebKit2, _Gdk, GLib = desktop_libraries()

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:17890'
destination = Path(__file__).resolve().parent.parent
window = Gtk.Window(title='Clashctl UI · 界面验证')
window.set_default_size(1250, 820)
view = WebKit2.WebView()
window.add(view)
window.show_all()
failures = []


def js(script, callback):
    def done(widget, result, _data):
        try:
            value = widget.run_javascript_finish(result).get_js_value().to_string()
            callback(json.loads(value))
        except Exception as exc:
            failures.append(str(exc))
            Gtk.main_quit()
    view.run_javascript('JSON.stringify(' + script + ')', None, done, None)


def snap(filename, callback):
    def done(widget, result, _data):
        try:
            widget.get_snapshot_finish(result).write_to_png(str(destination / filename))
            callback()
        except Exception as exc:
            failures.append(str(exc))
            Gtk.main_quit()
    view.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, done, None)


def assert_result(result):
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if not result.get('ok'):
        failures.append(result)


def verify():
    js('({ok:!!state && state.online, title:document.title, proxies:state ? Object.keys(state.proxies).length : 0, horizontalOverflow:document.documentElement.scrollWidth > innerWidth, down:document.getElementById("download-speed").textContent})', after_dashboard)
    return False


def after_dashboard(result):
    assert_result(result)
    snap('preview.png', proxies)


def proxies():
    js('(()=>{navigate("proxies");return {ok:document.querySelectorAll(".node-card").length > 0,page,nodeCards:document.querySelectorAll(".node-card").length}})()', after_proxies)


def after_proxies(result):
    assert_result(result)
    snap('preview-proxies.png', profiles)


def profiles():
    js('(()=>{navigate("profiles");return {ok:document.querySelectorAll(".profile-card").length > 0,page}})()', connections)


def connections(result):
    assert_result(result)
    js('(()=>{navigate("connections");document.getElementById("connection-search").value="NO_MATCH_QA_QUERY";renderConnections();return {ok:document.getElementById("connection-list").textContent.includes("暂无匹配"),page}})()', dialogs)


def dialogs(result):
    assert_result(result)
    js('(()=>{document.getElementById("add-profile").click();const ok=document.getElementById("modal").open && document.querySelectorAll("#modal input").length===2;document.getElementById("modal").close();navigate("rules");return {ok,dialog:"subscription"}})()', rules_wait)


def rules_wait(result):
    assert_result(result)
    GLib.timeout_add(1700, rules_check)


def rules_check():
    js('({ok:document.querySelectorAll("#rule-list tr").length>1,rules:document.querySelectorAll("#rule-list tr").length})', logs)
    return False


def logs(result):
    assert_result(result)
    js('(()=>{navigate("logs");return {ok:true}})()', logs_wait)


def logs_wait(_result):
    GLib.timeout_add(1000, logs_check)


def logs_check():
    js('({ok:document.querySelectorAll(".log-line").length>0,logs:document.querySelectorAll(".log-line").length})', dark)
    return False


def dark(result):
    assert_result(result)
    js('(()=>{navigate("dashboard");theme("dark");return {ok:document.body.classList.contains("dark")}})()', dark_snap)


def dark_snap(result):
    assert_result(result)
    GLib.timeout_add(300, lambda: (snap('preview-dark.png', mobile), False)[1])


def mobile():
    js('(()=>{theme("light");return true})()', lambda _result: None)
    window.resize(480, 900)
    GLib.timeout_add(700, mobile_check)


def mobile_check():
    js('({ok:document.documentElement.scrollWidth <= innerWidth,width:innerWidth,scrollWidth:document.documentElement.scrollWidth})', mobile_snap)
    return False


def mobile_snap(result):
    assert_result(result)
    snap('preview-mobile.png', Gtk.main_quit)


view.load_uri(base + '/')
GLib.timeout_add(5500, verify)
GLib.timeout_add(35000, lambda: (failures.append('GUI check timed out'), Gtk.main_quit(), False)[2])
Gtk.main()
window.destroy()
if failures:
    print('FAILED:', failures, file=sys.stderr)
    sys.exit(1)
print('Desktop UI checks passed')
