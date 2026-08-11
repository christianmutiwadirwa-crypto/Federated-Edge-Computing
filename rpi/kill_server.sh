#!/bin/bash
echo "Killing Raspberry Pi Edge Node server..."
pkill -f "python.*main.py"
echo "Server killed (if it was running)."
