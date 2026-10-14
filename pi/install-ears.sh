#!/bin/bash
# One-time setup of Jarvis's ears on the Pi with the Anker S330 (through the powered hub).
# Run ON THE PI, from the folder that holds jarvis-ears.py, ha-token.txt and this pi/ folder:
#   cd /home/adil/jarvis && bash pi/install-ears.sh
set -e
echo "== 1/5 system packages (audio player, PortAudio for the mic)"
sudo apt-get update -qq
sudo apt-get install -y -qq mpg123 alsa-utils portaudio19-dev python3-venv python3-dev

echo "== 2/5 Python toolbox at /home/adil/jarvis-ears-env"
[ -d /home/adil/jarvis-ears-env ] || python3 -m venv /home/adil/jarvis-ears-env
/home/adil/jarvis-ears-env/bin/pip install -q --upgrade pip
/home/adil/jarvis-ears-env/bin/pip install -q websockets numpy sounddevice "openwakeword>=0.6"

echo "== 3/5 make the S330 the default speaker and mic"
CARD=$(aplay -l | grep -i "s330\|anker\|usb audio" | head -1 | sed -E 's/card ([0-9]+).*/\1/')
if [ -z "$CARD" ]; then
  echo "   S330 not found by aplay -l. Plug it in through the powered hub and run this again."
  exit 1
fi
cat > /home/adil/.asoundrc <<ASOUND
defaults.pcm.card $CARD
defaults.ctl.card $CARD
ASOUND
echo "   S330 is ALSA card $CARD"

echo "== 4/5 sound check: you should hear a tone from the S330"
speaker-test -t sine -f 660 -l 1 -s 1 >/dev/null 2>&1 || true

echo "== 5/5 install and start the service"
sudo cp pi/jarvis-ears.service /etc/systemd/system/jarvis-ears.service
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis-ears
sleep 3
sudo systemctl --no-pager status jarvis-ears | head -12
echo
echo "Done. Say \"Hey Jarvis\". Logs: journalctl -u jarvis-ears -f"
