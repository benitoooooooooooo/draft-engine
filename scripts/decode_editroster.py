#!/usr/bin/env python3
"""Decode the team page's 16 lineup selects: names, current values, option format."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import load_config, launch_headless

BUN = os.path.expanduser('~/.bun/bin/bun')
EVAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_cdp_eval.js')

JS = """JSON.stringify({
  selects: [...document.querySelectorAll('select')].map((s, i) => ({
    i, name: s.name,
    value: s.value,
    label: s.closest('tr,div')?.innerText.replace(/\\s+/g,' ').slice(0, 45),
    n_opts: s.options.length,
    first_opts: [...s.options].slice(0, 3).map(o => o.value.slice(0, 55))
  })).filter(s => s.name),
  form: [...document.querySelectorAll('form')].map(f => ({
    action: f.action.slice(0, 80), method: f.method,
    fields: [...f.querySelectorAll('input,select,button')].slice(0, 10).map(
      e => e.tagName + ':' + (e.name || e.type))
  })).filter(f => f.fields.length)
})"""


def main():
    cfg = load_config()
    launch_headless()
    url = f"https://football.fantasysports.yahoo.com/f1/{cfg['league_id']}/4"
    r = subprocess.run([BUN, EVAL, url, JS], capture_output=True, text=True, timeout=150)
    line = (r.stdout.strip().splitlines() or ['FAIL'])[-1]
    try:
        d = json.loads(line)
        d = json.loads(d) if isinstance(d, str) else d
    except Exception:
        d = {'raw': line[:800]}
    print(json.dumps(d, indent=1)[:3500])


if __name__ == '__main__':
    main()
