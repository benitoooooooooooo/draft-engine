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
  // starters page: one table per team. Capture all; label blocks by header text.
  const tables = [...document.querySelectorAll('table')];
  const teams = [];
  for (const t of tables) {
    const txt = t.innerText;
    if (!/QB|RB/.test(txt)) continue;
    // team name: walk up to a container that has a team link
    let el = t, teamName = '', teamId = '';
    for (let up = 0; up < 6 && el; up++) {
      el = el.parentElement;
      if (!el) break;
      const a = el.querySelector && el.querySelector('a[href*="/f1/968508/"]');
      if (a) {
        const m = a.href.match(/f1\\/968508\\/(\\d+)/);
        if (m && ['1','2','3','4','5','6','7','8','9','10'].includes(m[1])) {
          teamId = m[1]; teamName = a.innerText.trim();
        }
      }
      if (teamId) break;
    }
    const rows = [];
    [...t.querySelectorAll('tr')].forEach(tr => {
      const cells = [...tr.querySelectorAll('td')];
      if (cells.length < 2) return;
      const slot = cells[0].innerText.trim().toUpperCase();
      if (!/^(QB|RB|WR|TE|K|DEF|FLEX|BN|IR|W|R|T|WR-RB-TE|[A-Z\\/ ]{1,8})$/.test(slot)) return;
      const nameEl = cells[1].querySelector('a.name');
      if (!nameEl) return;
      const inj = cells[1].querySelector('.F-injury span[title]');
      rows.push({slot, name: nameEl.innerText.trim(),
                 player_id: nameEl.getAttribute('data-ys-playerid'),
                 injury: inj ? inj.getAttribute('title') : ''});
    });
    if (rows.length >= 12 && teamId) teams.push({team_id: teamId, team_name: teamName, rows});
  }
  return JSON.stringify({teams});
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
    me = str(cfg.get('team_id', 4))
    for t in data.get('teams', []):
        tag = ' <-- MINE' if t['team_id'] == me else ''
        print(f"Team {t['team_id']:>2} {t['team_name']:<28} ({len(t['rows'])} slots){tag}")
        if t['team_id'] == me:
            for row in t['rows']:
                flag = f" [{row['injury']}]" if row['injury'] else ''
                print(f"    {row['slot']:<6} {row['name']:<24} pid={row['player_id']}{flag}")


if __name__ == '__main__':
    main()
