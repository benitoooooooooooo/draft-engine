#!/bin/bash
# Local-approvals punch-list for the mini (run while physically/SSH'd with sudo):
#
# 1) NEVER SLEEP ON AC — cron jobs die if the box is dozing:
#      sudo pmset -c sleep 0 displaysleep 10 disksleep 10
#    Verify after: pmset -g custom | grep "sleep"  (AC sleep should read 0)
#
# 2) One-time Yahoo login (opens real Chrome window on the mini's console):
#      ~/draft-engine/.venv/bin/python ~/draft-engine/scripts/yahoo_session.py launch --headful
#    ...then in that window go to https://fantasysports.yahoo.com and sign in.
#    Close the window when done — cookies persist in ~/yahoo-bot/chrome-profile.
#
# 3) (only if step 1 can't run before Thursday lock) scheduled wake fallback:
#      sudo pmset repeat wakeorpoweron MTWRFSU 18:55:00
#
# Everything else runs unattended. To confirm from anywhere after:
#      ssh mini 'pmset -g custom | grep -A6 "AC Power"'
