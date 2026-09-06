#!/usr/bin/env python3
"""Apply a lineup (yellow mode).

  .venv/bin/python scripts/apply_lineup.py            # DRY RUN: validate only
  .venv/bin/python scripts/apply_lineup.py --commit   # actually submit to Yahoo

Plan comes from optimize_lineup.py logic. Safety:
  - refuses to commit unless slot counts are exactly legal (1QB 2RB 2WR TE W/R/T K DEF)
  - refuses unknown pids / ineligible slots
  - after commit, re-reads the starters page and verifies the started set
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import load_config, launch_headless
from optimize_lineup import (EVAL, BUN, JS, proj_from_cell, pos_from_cell,
                             season_weekly, load_draft_positions, plan_lineup, FLEX_OK)

REQUIRED = {'QB': 1, 'RB': 2, 'WR': 2, 'TE': 1, 'W/R/T': 1, 'K': 1, 'DEF': 1}

# set selects to target slots; optionally submit the editroster form
SET_JS = """(() => {
  const target = %s;
  const errors = [];
  for (const [pid, slot] of Object.entries(target)) {
    const s = document.querySelector('select[name=\"' + pid + '\"]');
    if (!s) { errors.push('no select for ' + pid); continue; }
    const ok = [...s.options].some(o => o.value === slot);
    if (!ok) { errors.push(pid + ' cannot be ' + slot); continue; }
    s.value = slot;
    s.dispatchEvent(new Event('change', {bubbles: true}));
  }
  return JSON.stringify({errors});
})()"""

SUBMIT_JS = """(() => {
  const f = [...document.querySelectorAll('form')].find(
      x => /editroster/.test(x.action));
  if (!f) return 'no form';
  const btn = f.querySelector('button[type=submit], input[type=submit]') ||
              [...f.querySelectorAll('button,a')].find(b => /submit|save|change/i.test(b.innerText));
  if (btn) { btn.click(); return 'clicked ' + (btn.innerText || btn.type); }
  f.submit(); return 'form.submit()';
})()"""


def evaluate(url, js, timeout=150):
    r = subprocess.run([BUN, EVAL, url, js], capture_output=True, text=True, timeout=timeout)
    line = (r.stdout.strip().splitlines() or ['FAIL'])[-1]
    try:
        d = json.loads(line)
        return json.loads(d) if isinstance(d, str) else d
    except Exception:
        return {'raw': line[:300]}


def current_plan(base):
    data = evaluate(base + '/starters', JS)
    if not isinstance(data, dict) or 'rows' not in data:
        sys.exit(f'starters fetch failed: {data}')
    draft_pos, weekly = load_draft_positions(), season_weekly()
    players = []
    for p in data['rows']:
        proj = proj_from_cell(p['cell'])
        if proj is None:
            proj = weekly.get(p['name'], 0.0)
        pos = (pos_from_cell(p['cell']) or draft_pos.get(p['name'])
               or {'W/R/T': 'FLEX'}.get(p['slot'], p['slot']))
        players.append({**p, 'proj': proj, 'pos': pos})
    chosen, _ = plan_lineup(players)
    target = {p['pid']: slot for slot, p in chosen}
    current = {p['pid']: p['slot'] for p in players if p['is_start']}
    return target, current, {p['pid']: p['name'] for p in players}


def main():
    commit = '--commit' in sys.argv
    cfg = load_config()
    launch_headless()
    base = f"https://football.fantasysports.yahoo.com/f1/{cfg['league_id']}/{cfg.get('team_id',4)}"
    target, current, names = current_plan(base)

    # validate slot counts
    from collections import Counter
    counts = Counter(target.values())
    for slot, n in REQUIRED.items():
        if counts.get(slot, 0) != n:
            sys.exit(f'ABORT: {slot} count {counts.get(slot,0)} != {n}')

    changes = {pid: s for pid, s in target.items() if current.get(pid) != s}
    if not changes:
        print('✅ lineup already optimal; nothing to do')
        return
    print('planned moves:')
    for pid, s in changes.items():
        frm = current.get(pid, 'BN')
        print(f"  {names.get(pid, pid):<22} {frm:<6} -> {s}")

    if not commit:
        print('\nDRY RUN — pass --commit to submit')
        return

    url = base  # team page hosts the selects + form
    res = evaluate(url, SET_JS % json.dumps(target))
    if res.get('errors'):
        sys.exit(f'ABORT setting selects: {res["errors"]}')
    print('selects set, submitting…')
    print(evaluate(url, SUBMIT_JS))
    # verify
    import time
    time.sleep(5)
    _, recheck, _ = current_plan(base)
    ok = all(recheck.get(pid) == s for pid, s in target.items()
             if s in REQUIRED or True)
    mism = {pid: (recheck.get(pid), s) for pid, s in target.items()
            if recheck.get(pid) != s}
    if mism:
        print('⚠ post-submit verification mismatch (manual check!):',
              {names.get(k, k): v for k, v in mism.items()})
    else:
        print('✅ LINEUP SUBMITTED AND VERIFIED')


if __name__ == '__main__':
    main()
