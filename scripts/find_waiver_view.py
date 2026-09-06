#!/usr/bin/env python3
"""Find the live waiver/free-agent view in Yahoo f1. Tests the routes the
league nav exposes and reports which render real tables."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import load_config, launch_headless

BUN = os.path.expanduser('~/.bun/bin/bun')
EVAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_cdp_eval.js')

JS = ("JSON.stringify({title: document.title.slice(0,50), trs: "
      "document.querySelectorAll('table tr').length, sample: [...document.querySelectorAll("
      "'table tr')].slice(1,5).map(tr=>[...tr.querySelectorAll('td')].map("
      "c=>c.innerText.trim().replace(/\\s+/g,' ').slice(0,28)).slice(0,6))})")

CANDIDATES = [
    'players?status=A',
    'players?pos=RB&status=A',
    '4/add?pos=RB',
    'transactions',
    'buzzindex',
]


def main():
    cfg = load_config()
    launch_headless()
    base = f"https://football.fantasysports.yahoo.com/f1/{cfg['league_id']}"
    for path in CANDIDATES:
        url = base + '/' + path
        r = subprocess.run([BUN, EVAL, url, JS], capture_output=True, text=True, timeout=150)
        line = (r.stdout.strip().splitlines() or ['FAIL'])[-1]
        try:
            d = json.loads(line)
            d = json.loads(d) if isinstance(d, str) else d
        except Exception:
            d = {'raw': line[:150]}
        print(f"\n== {path}")
        print('  ', json.dumps(d)[:600])


if __name__ == '__main__':
    main()
