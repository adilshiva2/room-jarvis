#!/bin/zsh
# Run the Jarvis Doctor report on the Pi from the Mac (asks for the Pi password).
ssh -t adil@jarvis-pi.local 'sudo python3 /home/adil/jarvis/jarvis-doctor.py report'
