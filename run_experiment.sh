#!/usr/bin/env bash
# Single entry point for thesis reproduction and experiment execution.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -z "${PYTHON:-}" ]]; then
    if command -v python3 >/dev/null 2>&1; then PYTHON=python3
    elif command -v python >/dev/null 2>&1; then PYTHON=python
    else printf 'error: Python 3 is required; set PYTHON to its executable.\n' >&2; exit 1
    fi
fi
exec "$PYTHON" analysis/run_experiment.py "$@"
