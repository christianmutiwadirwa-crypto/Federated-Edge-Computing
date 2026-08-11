#!/bin/bash
echo "Starting Raspberry Pi Edge Node Server..."
cd "$(dirname "$0")/src" || exit
python3 main.py
