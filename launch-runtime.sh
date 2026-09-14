#!/usr/bin/env bash
set -euo pipefail
skipper_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
skipper_data="${XDG_DATA_HOME:-$HOME/.local/share}/skipper"
skipper_python="$skipper_data/venv/bin/python"
if [[ ! -x "$skipper_python" && -x "$skipper_root/.venv/bin/python" ]]; then
  skipper_python="$skipper_root/.venv/bin/python"
fi
if [[ ! -x "$skipper_python" ]]; then
  echo "Skipper needs setup: python '$skipper_root/plugin_setup.py' install" >&2
  exit 1
fi
exec "$skipper_python" "$skipper_root/$1" "${@:2}"
