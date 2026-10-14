#!/bin/zsh
# Start Jarvis's ears on this Mac (wake word -> Home Assistant). One copy only.
pgrep -f jarvis-ears.py >/dev/null && { echo "ears already running (pkill -f jarvis-ears.py to stop)"; exit 1; }
cd ~/jarvis && source ~/jarvis-ears-env/bin/activate && exec python3 jarvis-ears.py
