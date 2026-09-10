#!/bin/bash
cd /workspace/vampire-survivors-bot
export DISPLAY=:6
export QT_QPA_PLATFORM=xcb
export PYTHONUNBUFFERED=1
exec ./.venv/bin/python -u main.py
