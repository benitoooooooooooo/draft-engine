#!/usr/bin/env python3
"""Pull structured data out of Yahoo pages via in-page JS (CDP eval)."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import BASE, load_config, launch_headless

BUN = os.path.expanduser('~/.bun/bin/bun')
EVAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_cdp_eval.js')


def evaluate(nav_url, expr, out=None):
    launch_headless()
    r = subprocess.run([BUN, EVAL, nav_url, expr] + ([out] if out else []),
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print('ERR:', r.stderr[:300], r.stdout[:200])
        return None
    line = [l for l in r.stdout.splitlines() if l.strip()][-1] if r.stdout.strip() else ''
    if out:
        return json.load(open(out))
    try:
        return json.loads(line)
    except (json.JSONDecodeError, IndexError):
        return line


SCORING_JS = '''
(() => {
  const out = {roster: [], scoring: {}, league: {}};
  const txt = document.body.innerText;
  // league basics
  const lm = txt.match(/League Name\\n([^\\n]+)/); if(lm) out.league.name = lm[1];
  // roster positions line e.g. "Starting Positions" / "QB RB WR WR TE FLEX K DEF BN x6"
  // scoring table: find rows like "Passing Yards  0.04" via table scan
  document.querySelectorAll('table tr').forEach(tr => {
    const cells = [...tr.querySelectorAll('td,th')].map(c => c.innerText.trim());
    if (cells.length >= 2) {
      const label = cells[0];
      const val = cells.find(c => /^-?[\\d.]+$/.test(c));
      if (label && val && label.length < 40 && /yards|touchdown|interception|fumble|reception|sack|extra|field|point|return|tackle|safety|completion/i.test(label)) {
        out.scoring[label] = parseFloat(val);
      }
    }
  });
  // roster requirements block
  const rs = txt.match(/Roster Positions([\\s\\S]{0,400})Starting Positions/);
  if (rs) out.league.roster_text = rs[1].replace(/\\n+/g,' | ').slice(0,300);
  return JSON.stringify(out);
})()
'''


def main():
    cfg = load_config()
    lid = cfg['league_id']
    base = f'https://football.fantasysports.yahoo.com/f1/{lid}'
    data = evaluate(f'{base}/settings', SCORING_JS)
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        print('scoring extraction failed:', str(data)[:200])
        data = {}
    out = os.path.join(BASE, 'season_config.json')
    existing = {}
    if os.path.exists(out):
        existing = json.load(open(out))
    existing.update({
        'league_id': lid, 'team_id': 4, 'my_team': 'Straight to Jail',
        'scoring': data.get('scoring', {}), 'league': data.get('league', {})})
    json.dump(existing, open(out, 'w'), indent=2)
    print(json.dumps(existing, indent=2)[:1500])


if __name__ == '__main__':
    main()
