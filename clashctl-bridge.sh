#!/usr/bin/env bash
# Only the bridge's allow-listed actions are passed as separate arguments.
export CLASHCTL_HOME="${CLASHCTL_HOME:-$HOME/.clashctl}"
source "$CLASHCTL_HOME/scripts/cmd/clashctl.sh" || exit 1
clashctl "$@"
result=$?
if [ "$result" -ne 0 ] && [ -t 0 ]; then
    printf '\n操作未完成。按 Enter 关闭此窗口…'
    read -r _ui_reply
fi
exit "$result"
