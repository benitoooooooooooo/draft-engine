#!/usr/bin/env python3
"""Probe Yahoo f1 subpage routes: which exist, row counts, first data sample."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import load_config, launch_headless

BUN = os.path.expanduser('~/.bun/bin/bun')
EVAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_cdp_eval.js')

JS = ('JSON.stringify({title: document.title.slice(0, 60), '
      'rows: [...document.querySelectorAll("table tr")].slice(0, 4)'
      '.map(tr => [...tr.querySelectorAll("td,th")].map('
      'c => c.innerText.trim().replace(/\\s+/g, " ").slice(0, 30)).slice(0, 6))})')


def probe(path):
    cfg = load_config()
    url = f"https://football.fantasysports.yahoo.com/f1/{cfg['league_id']}/{path}"
    r = subprocess.run([BUN, EVAL, url, JS], capture_output=True, text=True, timeout=120)
    out = r.stdout.strip().splitlines()
    if not out:
        return None
    try:
        return json.loads(json.loads(out[-1])) if out[-1].startswith('"') else json.loads(out[-1])
    except (json.JSONDecodeError, ValueError):
        return {'raw': out[-1][:150]}


if __name__ == '__main__':
    launch_headless()
    for path in sys.argv[1:] or ['transactions', 'waivers', 'freeagents', 'movelist', 'playoffs']:
        d = probe(path)
        if d is None:
            print(f'{path:<14} FETCH FAILED')
            continue
        t = d.get('title', str(d)[:80])
        print(f'{path:<14} {t}')
        for row in d.get('rows', [])[:2]:
            print('    ', row)
