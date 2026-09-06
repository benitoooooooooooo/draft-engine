#!/usr/bin/env python3
"""Extract the current-week starters table from Yahoo, in-page via JS."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import BASE, load_config, launch_headless

BUN = os.path.expanduser('~/.bun/bin/bun')
EVAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_cdp_eval.js')

JS = '''
(() => {
  // starters page: one table per team, 2 cells (Pos, Player). Find ours.
  const tables = [...document.querySelectorAll('table')];
  const ours = tables.find(t => t.innerText.includes('Christian McCaffrey') &&
                                t.innerText.includes('Jayden Daniels'));
  if (!ours) return JSON.stringify({error: 'team table not found', tables: tables.length});
  const rows = [];
  [...ours.querySelectorAll('tr')].forEach(tr => {
    const cells = [...tr.querySelectorAll('td')];
    if (cells.length < 2) return;
    const slot = cells[0].innerText.trim();
    if (!/^(QB|RB|WR|TE|K|DEF|FLEX|BN|IR)$/.test(slot)) return;
    const nameEl = cells[1].querySelector('a.name');
    const inj = cells[1].querySelector('.F-injury span[title]');
    const proj = cells[1].innerText.match(/(\\d+\\.\\d+)\\s*proj/i);
    rows.push({slot, name: nameEl ? nameEl.innerText.trim() : '',
               player_id: nameEl ? nameEl.getAttribute('data-ys-playerid') : null,
               injury: inj ? inj.getAttribute('title') : ''});
  });
  const header = ours.closest('div')?.parentElement?.innerText.slice(0, 80) || '';
  return JSON.stringify({count: rows.length, rows});
})()
'''


def main():
    cfg = load_config()
    base = f"https://football.fantasysports.yahoo.com/f1/{cfg['league_id']}/{cfg.get('team_id', 4)}"
    launch_headless()
    out = os.path.join(BASE, 'scrape', 'starters.json')
    r = subprocess.run([BUN, EVAL, base + '/starters', JS, out],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not os.path.exists(out):
        print('ERR:', r.stderr[:300], r.stdout[:200]); return
    raw = open(out).read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print('RAW head:', raw[:400]); return
    print(f"rows matched: {data.get('count')}")
    for row in data.get('rows', []):
        print(f"  {row['pos_req']:<5} {row['name']:<24} pid={row['player_id']} "
              f"inj={row['injury'] or '-':<12} game={row['game'][:22]}")


if __name__ == '__main__':
    main()
