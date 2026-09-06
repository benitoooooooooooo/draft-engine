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
  const rows = [];
  document.querySelectorAll('table tr').forEach(tr => {
    const cells = [...tr.querySelectorAll('td')].map(c => c.innerText.trim().replace(/\\n+/g,' '));
    if (cells.length >= 3 && /^(QB|RB|WR|TE|K|DEF|FLEX|BN|IR)$/.test(cells[0])) {
      const nameEl = tr.querySelector('a.name');
      const pid = nameEl ? nameEl.getAttribute('data-ys-playerid') : null;
      const inj = tr.querySelector('.F-injury span[title]');
      const game = tr.querySelector('.ysf-game-status a');
      rows.push({pos_req: cells[0], name: nameEl ? nameEl.innerText.trim() : cells[1],
                 player_id: pid, row_cells: cells.slice(0,6),
                 injury: inj ? inj.getAttribute('title') : '',
                 game: game ? game.innerText.trim() : '',
                 started: !!(nameEl && nameEl.closest('tr') && tr.querySelector('input:checked, .selected'))
                });
    }
  });
  return JSON.stringify({count: rows.length, rows: rows.slice(0, 20)}, null, 1);
})()
'''


def main():
    cfg = load_config()
    base = f"https://football.fantasysports.yahoo.com/f1/{cfg['league_id']}/{cfg.get('team_id', 4)}"
    launch_headless()
    r = subprocess.run([BUN, EVAL, base + '/starters', JS],
                       capture_output=True, text=True, timeout=180)
    line = [l for l in r.stdout.splitlines() if l.strip()][-1]
    try:
        data = json.loads(json.loads(line)) if line.strip().startswith('"') else json.loads(line)
    except json.JSONDecodeError:
        print('RAW:', line[:2000]); return
    print(f"rows matched: {data.get('count')}")
    for row in data.get('rows', []):
        print(f"  {row['pos_req']:<5} {row['name']:<24} pid={row['player_id']} "
              f"inj={row['injury'] or '-':<12} game={row['game'][:22]} cells={row['row_cells'][:3]}")
    out = os.path.join(BASE, 'scrape', 'starters.json')
    json.dump(data, open(out, 'w'), indent=2)


if __name__ == '__main__':
    main()
