#!/usr/bin/env python3
"""Probe Yahoo endpoints from wherever it's run — find which data paths work
without OAuth so we know what Chrome-login buys us vs plain HTTP."""
import json
import sys
import requests

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}
LEAGUE = '968508'

CANDIDATES = [
    ('api.fantasysports official', f'https://api.fantasysports.yahoo.com/fhl/3/leagues/{LEAGUE}'),
    ('legacy json format', f'https://fantasysports.yahoo.com/football/league/{LEAGUE}/teams?format=json'),
    ('site xhr league', f'https://fantasysports.yahoo.com/football/ajax/league_summaries?league_id={LEAGUE}'),
    ('public standings', f'https://fantasysports.yahoo.com/football/league/{LEAGUE}/standings'),
    ('page html', f'https://fantasysports.yahoo.com/football/league/{LEAGUE}/teams'),
    ('player ids csv', 'https://s.yimg.com/xe/open/fantasy/games/nfl/player_ids.csv'),
    ('scoreboard', 'https://api.fantasysports.yahoo.com/fhl/3/games/nfl/scoreboard'),
]

for name, url in CANDIDATES:
    try:
        r = requests.get(url, headers=UA, timeout=15, allow_redirects=False)
        loc = r.headers.get('location', '')[:70]
        body = r.text[:120].replace('\n', ' ')
        print(f"[{r.status_code}] {name:<26} {len(r.content):>8}b  loc={loc}")
        print(f"      head: {body}")
    except Exception as e:
        print(f"[ERR] {name:<26} {type(e).__name__}: {str(e)[:80]}")
    print()
