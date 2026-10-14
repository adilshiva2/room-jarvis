#!/bin/zsh
# Flash jarvis-node1 over the air (turn the strip OFF first). Falls back to asking for USB.
cd ~/jarvis && source ~/jarvis-env/bin/activate && esphome run jarvis-node1.yaml "$@"
