#!/bin/zsh
# Open the Nucleus (Jarvis's face) full screen on this Mac. Needs the bridge running (start-bridge.sh).
URL="http://localhost:8802/"
if ! curl -s -o /dev/null --max-time 2 "$URL"; then
  echo "The bridge is not running (start it in another tab: ~/jarvis/scripts/start-bridge.sh)."
  echo "Opening the demo instead, so you can still see it move."
  URL="file://$HOME/jarvis/jarvis-nucleus.html?demo=1"
fi
if [ -d "/Applications/Google Chrome.app" ]; then
  open -na "Google Chrome" --args --new-window --app="$URL" --start-fullscreen
else
  open "$URL"
  echo "Press F on the page for fullscreen."
fi
