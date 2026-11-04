#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
if [[ -f "$project_dir/install.json" ]]; then
    exec /usr/bin/python3 "$project_dir/scripts/install_app.py" --uninstall --prefix "$project_dir"
fi
exec /usr/bin/python3 "$project_dir/scripts/install_app.py" --uninstall "$@"
