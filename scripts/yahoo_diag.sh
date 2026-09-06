#!/bin/bash
# Yellow-mode auth diagnostic: fresh bot Chrome, CDP tab inspection, league fetch.
cd ~/draft-engine
pkill -f "Google Chrome" 2>/dev/null; sleep 2
.venv/bin/python scripts/yahoo_session.py launch --headful
sleep 2
echo "=== tabs ==="
curl -s http://127.0.0.1:9333/json | .venv/bin/python -c "
import json,sys
for t in json.load(sys.stdin):
    if t['type']=='page': print(' ', t['url'][:100])
"
echo "=== navigate to league teams via existing tab (PUT /json/new) ==="
TAB=$(curl -s -X PUT "http://127.0.0.1:9333/json/new?url=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("https://fantasysports.yahoo.com/football/league/968508/teams"))' )" | .venv/bin/python -c "import json,sys;print(json.load(sys.stdin).get('id',''))")
sleep 8
echo "tab id: $TAB"
echo "=== final url of that tab ==="
curl -s http://127.0.0.1:9333/json | .venv/bin/python -c "
import json,sys
for t in json.load(sys.stdin):
    if t['type']=='page': print(' ', t['url'][:120])
"
echo "=== BEEF present in any rendered tab? ==="
.venv/bin/python scripts/scrape_league.py --pages teams 2>&1 | grep -v -i warn
grep -c BEEF ~/yahoo-bot/scrape/teams.html
