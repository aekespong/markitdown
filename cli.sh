#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$HOME/projects/markitdown"

exec python3 "$SCRIPT_DIR/convert_to_markdown.py" "$@"
