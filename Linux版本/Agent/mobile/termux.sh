#!/data/data/com.termux/files/usr/bin/sh
set -e
if ! command -v python >/dev/null 2>&1; then
  pkg update -y
  pkg install -y python
fi
if ! command -v node >/dev/null 2>&1; then
  pkg install -y nodejs
fi
cd "$(dirname "$0")/.."
exec python start.py --lan
