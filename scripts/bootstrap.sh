#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ ! -x .venv/bin/python ]; then
    python_bin="${LAB1_PYTHON:-python3.12}"
    "$python_bin" -c 'import sys; assert sys.version_info[:2] == (3,12), "Se requiere Python 3.12"'
    "$python_bin" -m venv .venv
fi
.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3,12), "El .venv existente debe usar Python 3.12"'
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
exec .venv/bin/python -m reposicion.bootstrap "$@"
