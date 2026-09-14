#!/usr/bin/env bash
set -euo pipefail
skipper_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$skipper_root/launch-runtime.sh" runtime.py "$@"
