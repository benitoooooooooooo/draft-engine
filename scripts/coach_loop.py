#!/usr/bin/env python3
"""
Coach Loop — deterministic (no-LLM) drafting assistant daemon.

Watches draft_state.json; on every new pick it recomputes the situation for
your team and writes a fresh coach_notes.txt the CLI displays before your
next prompt. Runs sub-100ms per event — the LLM agent stays out of the hot
path and handles judgment calls only when asked.

Usage:
  python3 scripts/coach_loop.py            # run in foreground (Ctrl-C out)
  run in background via terminal: python3 scripts/coach_loop.py &

What it writes to coach_notes.txt on each pick:
  - who just went + where we are in the snake (your next 2 picks)
  - run alerts (3+ same position in last 8)
  - your top 3 recs WITH the player's expert spread (contested picks flagged)
  - 'will not make it back' warnings for your #1 target
  - on-the-clock banner when you're up, with a decision-ready line

It also mirrors notes to coach_log.txt (append-only, timestamped) so the
Hermes agent can catch up on what happened while it was away.
"""
import sys
import os
import time
import json
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
from engine import load_draft_pool, DraftConfig, DraftState, ValuationEngine, Roster

STATE_PATH = os.path.join(ROOT, 'draft_state.json')
NOTES_PATH = os.path.join(ROOT, 'coach_notes.txt')
LOG_PATH = os.path.join(ROOT, 'coach_log.txt')
POOL_PATH = os.path.join(ROOT, 'data', 'draft_pool.json')
LEAGUE_PATH = os.path.join(ROOT, 'league.json')


def load_config():
    config = DraftConfig()
    order = []
    my_team = 0
    try:
        lg = json.load(open(LEAGUE_PATH))
        for k in ('qb_slots', 'rb_slots', 'wr_slots', 'te_slots', 'flex_slots',
                  'bench_slots', 'k_slots', 'dst_slots', 'teams'):
            if k in lg:
                setattr(config, k, lg[k])
        config.roster_spots = (config.qb_slots + config.rb_slots + config.wr_slots +
                               config.te_slots + config.flex_slots + config.k_slots +
                               config.dst_slots + config.bench_slots)
        order = lg.get('order', [])
        if lg.get('me') in order:
            my_team = order.index(lg['me'])
    except (OSError, ValueError):
        pass
    return config, order, my_team


def build_state(config, pool):
    """Reconstruct from the export the CLI writes on every pick."""
    if not os.path.exists(STATE_PATH):
        return DraftState(config, list(pool), {}), {}
    try:
        with open(STATE_PATH) as f:
            export = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return None, None  # mid-write; try next tick
    name_map = {p.name: p for p in pool}
    state = DraftState(config, list(pool), {})
    state.rosters = {i: Roster(i) for i in range(config.teams)}
    for pk in export.get('picks_made', []):
        pl = name_map.get(pk['player'])
        if pl is None:
            # off-pool placeholder pick (K/DST)
            continue
        tid = pk['team'] - 1
        state.rosters[tid].players.append(pl)
        state.picks_made.append((tid, pl))
        state.available = [p for p in state.available if p.sleeper_id != pl.sleeper_id]
        state.current_pick += 1
    return state, export


def fmt_next_picks(team, teams, rounds=2):
    """Slot -> pick numbers (snake)."""
    picks = []
    for r in range(rounds):
        if r % 2 == 0:
            picks.append(r * teams + team + 1)
        else:
            picks.append(r * teams + (teams - team))
    return picks


def build_notes(state, export, config, order, my_team):
    engine = ValuationEngine(state)
    c = config
    lines = []
    now = datetime.datetime.now().strftime('%H:%M:%S')
    last = export.get('picks_made', [])[-1] if export and export.get('picks_made') else None

    rnd = state.current_pick // c.teams + 1
    pick_in_round = state.current_pick % c.teams
    on_you = state.current_team() == my_team

    head = f"BEEF draft · {now} · R{rnd}P{pick_in_round + 1} ({state.current_pick}/{c.total_picks})"
    if last:
        head += f" · last: {last['player']} ({last['position']}) → {order[last['team']-1] if order else 'T'+str(last['team'])}"
    lines.append(head)

    nxt = fmt_next_picks(my_team, c.teams)
    your_picks = [p for p in nxt if p > state.current_pick]
    if your_picks:
        lines.append(f"Your next picks: #{', #'.join(str(p) for p in your_picks[:2])}")

    # run detection
    recent = [p for _, p in state.picks_made[-8:]]
    if len(recent) >= 4:
        from collections import Counter
        counts = Counter(p.position for p in recent)
        hot, hc = counts.most_common(1)[0]
        if hc >= 4:
            lines.append(f"⚠ {hot} RUN: {hc}/8 recent. Best {hot} left:"
                         f" {next((p.name for p in state.available if p.position == hot), 'NONE')}")

    # recommendations + urgency
    recs = engine.get_recommendations(my_team, 3)
    roster = state.rosters[my_team]
    lines.append("")
    lines.append("Engine says:")
    for i, r in enumerate(recs, 1):
        p = r['player']
        spread = f" (experts {p.rank_min}-{p.rank_max}{' CONTESTED' if p.rank_max - p.rank_min > 15 else ''})" if getattr(p, 'rank_std', 0) else ""
        until = state.picks_until_turn(my_team)
        will_last = engine.dropoff_risk(p, until)
        warn = ""
        if until > 0 and will_last > 0.65:
            warn = "  ⛔ WON'T LAST TO NEXT PICK"
        note = r.get('note', '')
        if r.get('opponent_pressure') and 'OPP' not in note:
            warn += "  👀 opponents need this"
        lines.append(f"  {i}. {p.name} {p.position} {p.team} · PPR {p.projected_pts:.0f} · VORP {r['vorp']:.0f}{spread}{warn}")
    if roster.players:
        rc = engine.roster_construction_score(my_team)
        if rc['balance_issues']:
            lines.append(f"⚠ roster: {', '.join(rc['balance_issues'])}")
    if on_you:
        lines.append("")
        lines.append(f">>> YOU ARE ON THE CLOCK ({pick_in_round + 1} of {c.teams} in round) — take #1 unless the note below overrides")
    return "\n".join(lines)


def main():
    config, order, my_team = load_config()
    pool = load_pool = load_draft_pool(POOL_PATH)
    print(f"coach_loop watching {STATE_PATH} (team: {order[my_team] if order else my_team})")
    last_mtime = 0.0
    while True:
        try:
            mtime = os.path.getmtime(STATE_PATH)
        except OSError:
            time.sleep(0.5)
            continue
        if mtime > last_mtime:
            last_mtime = mtime
            state, export = build_state(config, pool)
            if state is not None:
                notes = build_notes(state, export, config, order, my_team)
                with open(NOTES_PATH, 'w') as f:
                    f.write(notes + "\n")
                with open(LOG_PATH, 'a') as f:
                    f.write(notes + "\n" + "-" * 70 + "\n")
        time.sleep(0.1)


if __name__ == '__main__':
    main()
