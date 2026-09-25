#!/bin/bash
cd "$(dirname "$0")"
export DISPLAY=:6
export QT_QPA_PLATFORM=xcb
export PYTHONUNBUFFERED=1
exec ./.venv/bin/python -u main.py
