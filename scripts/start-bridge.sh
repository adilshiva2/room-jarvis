#!/bin/zsh
# Start the task bridge (voice tasks, reel + recruiting digests, photo drop). One copy only.
pgrep -f jarvis-tasks.py >/dev/null && { echo "bridge already running (pkill -f jarvis-tasks.py to stop)"; exit 1; }
cd ~/jarvis && source ~/jarvis-ears-env/bin/activate && exec python3 jarvis-tasks.py
