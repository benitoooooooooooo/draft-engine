#!/usr/bin/env python3
"""Inspect starters-page form controls: what do the click-and-submit
lineup changes actually look like in the DOM?"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import load_config, launch_headless

BUN = os.path.expanduser('~/.bun/bin/bun')
EVAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_cdp_eval.js')

JS = """JSON.stringify({
  inputs: document.querySelectorAll('input').length,
  radios: document.querySelectorAll('input[type=radio]').length,
  boxes: document.querySelectorAll('input[type=checkbox]').length,
  selects: document.querySelectorAll('select').length,
  buttons: [...document.querySelectorAll('button, a.button')]
      .map(b => b.innerText.trim().slice(0, 20)).filter(Boolean).slice(0, 15),
  formActions: [...document.querySelectorAll('form')].map(f => f.action).slice(0, 5),
  radioSamples: [...document.querySelectorAll('input[type=radio]')]
      .slice(0, 6).map(i => ({name: i.name, value: (i.value || '').slice(0, 40),
      checked: i.checked})),
  draggables: document.querySelectorAll('[draggable=true]').length
})"""


def main():
    cfg = load_config()
    launch_headless()
    base = f"https://football.fantasysports.yahoo.com/f1/{cfg['league_id']}/4"
    for url in (base, base + '/starters'):
        r = subprocess.run([BUN, EVAL, url, JS], capture_output=True, text=True, timeout=150)
        line = (r.stdout.strip().splitlines() or ['FAIL'])[-1]
        try:
            d = json.loads(line)
            d = json.loads(d) if isinstance(d, str) else d
        except Exception:
            d = {'raw': line[:300]}
        print(f"\n== {url.split(cfg['league_id'])[1] or '/(team page)'}")
        print(json.dumps(d, indent=1)[:1400])


if __name__ == '__main__':
    main()
