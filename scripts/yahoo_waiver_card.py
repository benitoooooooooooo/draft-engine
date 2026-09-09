#!/usr/bin/env python3
"""WAIVER CARD (cron --no-agent on the mini). Lists the league wire ranked
by season-avg weekly value, flags coverage for our injured/questionable
starters. Proposes only; agent submits claims after user ✅."""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, '/Users/benbrackett/draft-engine/scripts')
from yahoo_session import load_config, launch_headless
from optimize_lineup import BUN, EVAL, JS, pos_from_cell, season_weekly, load_draft_positions
from weekly_values import lookup as weekly_lookup

WIRE_JS = """JSON.stringify([...document.querySelectorAll('table tr')].map(tr => {
  const tds = [...tr.querySelectorAll('td')];
  if (tds.length < 4) return null;
  const nameEl = tds[2].querySelector('a.name') || tds[2].querySelector('a');
  if (!nameEl) return null;
  const txt = tds[2].innerText.replace(/\\s+/g, ' ');
  return {name: nameEl.innerText.trim(),
          cell: txt.slice(0, 120),
          rostered: tds.length >= 6 ? tds[tds.length-2].innerText.trim().slice(0, 8) : '',
          start: tds.length >= 6 ? tds[tds.length-1].innerText.trim().slice(0, 8) : ''};
}).filter(Boolean).slice(0, 80))"""


def extract(url, js):
    """Run JS on url via CDP; returns parsed result. Exits loudly with a
    Telegram-readable alert if Yahoo bounced us to the sign-in wall."""
    out = subprocess.run([BUN, EVAL, url, js], capture_output=True,
                         text=True, timeout=180)
    lines = out.stdout.strip().splitlines()
    if not lines:
        sys.exit('ALERT: Yahoo fetch returned nothing (CDP/chrome down on mini?). '
                 f'stderr: {out.stderr.strip()[:200]}')
    r = json.loads(lines[-1])
    r = json.loads(r) if isinstance(r, str) else r
    if isinstance(r, dict) and r.get('error'):
        # team table not found == almost always the login wall (200 + 0 tables)
        sys.exit('ALERT: YAHOO SESSION EXPIRED on the mini. Waiver card cannot '
                 'run. Re-login: ssh mini, then run '
                 '~/draft-engine/.venv/bin/python ~/draft-engine/scripts/'
                 'yahoo_session.py launch --headful and sign in (check "Stay '
                 'signed in").')
    return r


def main():
    cfg = load_config()
    launch_headless()
    lid = cfg['league_id']
    # our injury situation first
    team_url = f"https://football.fantasysports.yahoo.com/f1/{lid}/4"
    me = extract(team_url + '/starters', JS)
    injured = [(r['name'], r['injury'], r['slot']) for r in me.get('rows', [])
               if r['injury'] and r['is_start']]

    weekly, dpos = season_weekly(), load_draft_positions()
    wire = extract(f'https://football.fantasysports.yahoo.com/f1/{lid}/players?status=A',
                   WIRE_JS)
    if not isinstance(wire, list):
        sys.exit('ALERT: waiver-wire page returned unexpected shape '
                 f'(keys: {list(wire)[:5]}) — Yahoo DOM change?')

    rows, graded = [], 0
    for p in wire:
        pos = pos_from_cell(p['cell']) or dpos.get(p['name'])
        wk = weekly_lookup(p['name'])
        if wk:
            val, grade, opp = wk[0], wk[1], wk[2]
            graded += 1
        else:
            val, grade, opp = weekly.get(p['name'], 0.0), '', ''
        if pos and val > 0:
            rows.append((p['name'], pos, val, grade, opp))
    rows.sort(key=lambda x: -x[2])
    seen, top = set(), []
    for name, pos, val, grade, opp in rows:
        if name not in seen:
            seen.add(name)
            top.append((name, pos, val, grade, opp))

    L = ['🌊 WEEKLY WAIVER SWEEP — Straight to Jail',
         '   matchup-aware weekly consensus (incl FTN)', '─' * 44]
    if injured:
        L.append('⚠ Our injuries: ' + ', '.join(f'{n} [{i}]' for n, i, _ in injured))
    L.append('Best on the wire (season-avg/week):')
    for name, pos, val, grade, opp in top[:12]:
        g = f"{grade:<2}" if grade else '  '
        o = opp[:8] if opp else ''
        L.append(f'  {pos:<4} {name:<26} {g}{o:<9} {val:>5.1f}')
    L.append('─' * 44)
    L.append('reply with names to claim (agent submits), or ✅ for top-2 by position need')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
