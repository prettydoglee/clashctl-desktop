#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
app_prefix="${XDG_DATA_HOME:-$HOME/.local/share}/clashctl-desktop"
app_bin_dir="$HOME/.local/bin"
core_home="${CLASHCTL_HOME:-$HOME/.clashctl}"
download_proxy="${GH_PROXY:-}"
core_service=auto
web_only=false
skip_deps=false
skip_core=false
no_launch=false
tun_autostart=false
core_commit=4ec42a9f33108a16281bdad4eace7ccce94ae3b2

usage() {
    cat <<'HELP'
Clashctl Desktop 一键安装（Ubuntu / Debian，amd64 / arm64）

  bash install.sh [选项]

  --web                  仅安装浏览器控制台，无需 GTK / 桌面环境
  --no-launch            安装完成后不自动打开窗口
  --tun-autostart        额外安装 TUN 开机服务（需要 sudo 和 systemd）
  --skip-deps            不调用 apt；依赖由使用者预先提供
  --skip-clashctl        不下载 clashctl；要求指定目录内已有完整安装
  --prefix PATH          控制台安装目录，默认 ~/.local/share/clashctl-desktop
  --bin-dir PATH         命令目录，默认 ~/.local/bin
  --clashctl-home PATH   clashctl 安装目录，默认 ~/.clashctl
  --gh-proxy URL         可选 GitHub 下载代理前缀，默认直连
  --service MODE         clashctl 后端：auto / systemd-user / nohup
  -h, --help             显示帮助

安装器不会内置订阅或节点；首次打开后添加自己的 Clash / Mihomo 订阅。
请以普通用户运行，需要安装系统依赖时会调用 sudo。
HELP
}

need_value() {
    [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || { printf '参数 %s 缺少值\n' "$1" >&2; exit 2; }
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --web) web_only=true ;;
        --no-launch) no_launch=true ;;
        --tun-autostart) tun_autostart=true ;;
        --skip-deps) skip_deps=true ;;
        --skip-clashctl) skip_core=true ;;
        --prefix) need_value "$@"; app_prefix=$2; shift ;;
        --bin-dir) need_value "$@"; app_bin_dir=$2; shift ;;
        --clashctl-home) need_value "$@"; core_home=$2; shift ;;
        --gh-proxy) need_value "$@"; download_proxy=$2; shift ;;
        --service) need_value "$@"; core_service=$2; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf '未知选项：%s\n' "$1" >&2; exit 2 ;;
    esac
    shift
done

[[ $(uname -s) == Linux ]] || { printf '当前版本支持 Linux。\n' >&2; exit 1; }
[[ $EUID -ne 0 ]] || { printf '请以普通用户运行 bash install.sh，不要使用 sudo 启动整个安装器。\n' >&2; exit 1; }
case "$core_service" in auto|systemd-user|nohup) ;; *) printf '无效的 --service\n' >&2; exit 2 ;; esac
for destination in "$app_prefix" "$app_bin_dir" "$core_home"; do
    [[ $destination == /* && $destination != / ]] || { printf '安装路径必须是绝对路径，且不能是根目录。\n' >&2; exit 2; }
done
if [[ -n "$download_proxy" && ! "$download_proxy" =~ ^https?://[^[:space:]]+$ ]]; then
    printf '下载代理前缀必须是 http(s) URL。\n' >&2; exit 2
fi

if [[ "$skip_deps" != true ]]; then
    command -v apt-get >/dev/null || { printf '自动安装依赖支持 Ubuntu / Debian。其他发行版请先提供依赖，再加 --skip-deps。\n' >&2; exit 1; }
    command -v sudo >/dev/null || { printf '安装依赖需要 sudo；或自行安装依赖后加 --skip-deps。\n' >&2; exit 1; }
    printf '安装系统依赖…\n'
    sudo apt-get update
    packages=(python3 ca-certificates curl git tar gzip unzip)
    if [[ "$web_only" != true ]]; then
        packages+=(python3-gi python3-gi-cairo gir1.2-gtk-3.0 xdg-utils desktop-file-utils xterm)
        if apt-cache show gir1.2-webkit2-4.1 >/dev/null 2>&1; then
            packages+=(gir1.2-webkit2-4.1)
        elif apt-cache show gir1.2-webkit2-4.0 >/dev/null 2>&1; then
            packages+=(gir1.2-webkit2-4.0)
        else
            printf '软件源没有 WebKit GTK 包；可以使用 --web 安装浏览器版。\n' >&2; exit 1
        fi
    fi
    sudo apt-get install -y --no-install-recommends "${packages[@]}"
fi

command -v python3 >/dev/null || { printf '需要 Python 3.8 或更新版本。\n' >&2; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 8), "需要 Python >= 3.8"'

core_ready() {
    [[ -x "$core_home/bin/mihomo" && -f "$core_home/scripts/cmd/clashctl.sh" && -f "$core_home/data/runtime.yaml" ]] || return 1
    [[ ! -x "$core_home/bin/yq" ]] || return 0
    command -v yq >/dev/null || return 1
    case "$(yq --version 2>&1)" in *mikefarah*v4.*) return 0 ;; esac
    return 1
}

if core_ready; then
    printf '复用已有 clashctl：%s\n' "$core_home"
elif [[ "$skip_core" == true ]]; then
    printf '指定目录内没有完整的 clashctl / Mihomo 安装：%s\n' "$core_home" >&2; exit 1
else
    command -v git >/dev/null || { printf '安装 clashctl 需要 git。\n' >&2; exit 1; }
    printf '安装经过验证的 clashctl 版本…\n'
    core_source=$(mktemp -d)
    trap 'if [[ -n "${core_source:-}" ]]; then python3 -c "import shutil,sys; shutil.rmtree(sys.argv[1])" "$core_source"; fi' EXIT
    upstream=https://github.com/nelvko/clashctl.git
    [[ -z "$download_proxy" ]] || upstream="${download_proxy%/}/$upstream"
    git -C "$core_source" init --quiet
    git -C "$core_source" remote add origin "$upstream"
    git -C "$core_source" fetch --quiet --depth 1 origin "$core_commit"
    git -C "$core_source" checkout --quiet --detach FETCH_HEAD
    [[ $(git -C "$core_source" rev-parse HEAD) == "$core_commit" ]] || { printf '上游版本校验失败。\n' >&2; exit 1; }
    # Restrict the fresh controller to loopback before the first process starts.
    python3 - "$core_source/resources/mixin.yaml.example" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1])
text=p.read_text()
text,count=re.subn(r'^external-controller:.*$', 'external-controller: 127.0.0.1:9090',text,flags=re.M)
if count != 1: raise SystemExit('上游控制端口模板不匹配，已停止安装')
p.write_text(text)
PY
    CI=1 CLASHCTL_DOWNLOAD_TIMEOUT=180 bash "$core_source/install.sh" --local --home "$core_home" --service "$core_service" "--gh-proxy=$download_proxy"
fi

if ! core_ready; then
    printf 'clashctl 运行配置尚未生成。若同用户正在运行另一个目录的 TUN 内核，请复用原安装目录或先停止旧实例后重试。\n' >&2
    exit 1
fi

install_args=(--prefix "$app_prefix" --bin-dir "$app_bin_dir" --clashctl-home "$core_home")
[[ "$web_only" != true ]] || install_args+=(--web)
python3 "$project_dir/scripts/install_app.py" "${install_args[@]}"
if [[ "$tun_autostart" == true ]]; then
    command -v systemctl >/dev/null || { printf 'TUN 开机服务需要 systemd。\n' >&2; exit 1; }
    sudo /usr/bin/python3 "$app_prefix/scripts/tun_autostart.py" --uid "$EUID" --clashctl-home "$core_home"
fi

printf '\n安装完成。添加自己的订阅后即可使用。\n'
printf '启动：%s/clashctl-ui\n' "$app_bin_dir"
printf '诊断：%s/clashctl-ui --doctor\n' "$app_bin_dir"
printf '卸载界面：bash %q/uninstall.sh\n' "$app_prefix"
if [[ "$no_launch" != true && "$web_only" != true && -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    log_dir="${XDG_STATE_HOME:-$HOME/.local/state}/clashctl-ui"
    mkdir -p -- "$log_dir"
    chmod 700 -- "$log_dir"
    nohup "$app_bin_dir/clashctl-ui" >>"$log_dir/desktop.log" 2>&1 </dev/null &
else
    [[ "$web_only" != true ]] || printf '浏览器版：%s/clashctl-ui --serve\n' "$app_bin_dir"
fi
