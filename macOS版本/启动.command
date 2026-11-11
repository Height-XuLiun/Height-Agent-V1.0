#!/bin/sh
cd "$(dirname "$0")/Agent" || exit 1
PY=$(command -v python3 || command -v python)
[ -n "$PY" ] || { echo "Python 3.10+ required"; exit 1; }
exec "$PY" -u start.py
