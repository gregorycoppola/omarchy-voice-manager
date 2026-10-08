#!/usr/bin/env bash
set -euo pipefail
skipper_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export GSK_RENDERER="${GSK_RENDERER:-cairo}"
exec "$skipper_root/launch-runtime.sh" speech_preview.py "$@"
