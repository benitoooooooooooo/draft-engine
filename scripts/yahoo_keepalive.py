#!/usr/bin/env python3
"""KEEPALIVE (cron --no-agent on the mini). Touched every hour by cron, but
PROBES the league only on a randomized human-like cadence: roughly once per
10-16h, inside a 6am-10pm waking window, with the probability ramping so a
run is guaranteed by ~16h. Mimics someone checking the league in the AM and
PM, rolls Yahoo's session-idle clock, and stays silent when healthy.

Alerts are de-duped per expiry episode: one on detection, then every 24h.
"""
import json
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, '/Users/benbrackett/draft-engine/scripts')
from yahoo_session import BASE, load_config, launch_headless
from optimize_lineup import BUN, EVAL

STATE_PATH = os.path.join(BASE, 'keepalive_state.json')
PROBE = 'JSON.stringify({url: location.href, title: document.title})'
MIN_GAP_H, FORCE_GAP_H = 10.0, 16.0
WAKE_HOURS = range(6, 23)  # 6am..10pm local


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(st, f)
    os.replace(tmp, STATE_PATH)


def decide(now, st):
    """Should this hourly tick actually probe?"""
    lt = time.localtime(now)
    if lt.tm_hour not in WAKE_HOURS:
        return False  # asleep humans don't refresh league pages
    gap_h = (now - st.get('last_run', 0)) / 3600.0
    if gap_h < MIN_GAP_H:
        return False
    if gap_h >= FORCE_GAP_H:
        return True  # overdue: run it, even in a boring hour
    # ramp: 0% chance at 10h gap, 100% by 16h -> spread across midday/evening
    return random.random() < (gap_h - MIN_GAP_H) / (FORCE_GAP_H - MIN_GAP_H)


def probe(lid):
    launch_headless()
    url = f'https://football.fantasysports.yahoo.com/f1/{lid}/4/starters'
    out = subprocess.run([BUN, EVAL, url, PROBE], capture_output=True,
                         text=True, timeout=120)
    lines = out.stdout.strip().splitlines()
    if not lines:
        return 'cdp_down'
    r = json.loads(lines[-1])
    r = json.loads(r) if isinstance(r, str) else r
    if 'login.yahoo.com' in r.get('url', '') or r.get('title', '').startswith('Login'):
        return 'expired'
    return 'ok'


def main():
    now = time.time()
    st = load_state()
    if not decide(now, st):
        return  # silent tick
    lid = load_config()['league_id']
    status = probe(lid)
    st['last_run'] = now
    st['last_status'] = status
    if status == 'ok':
        st['alerted_at'] = 0  # reset the alert episode
    elif not st.get('alerted_at') or (now - st['alerted_at']) > 24 * 3600:
        st['alerted_at'] = now
        msg = ('ALERT: YAHOO SESSION EXPIRED (keepalive hit the login wall '
               'despite the heartbeat — likely a fresh Yahoo login elsewhere '
               'revoked it). Re-login on the mini: ~/draft-engine/.venv/bin/'
               'python ~/draft-engine/scripts/yahoo_session.py launch '
               '--headful')
        if status == 'cdp_down':
            msg = ('ALERT: yahoo keepalive got no CDP response (chrome down '
                   'on mini?). Check the gateway/Chrome on the mini.')
        save_state(st)
        print(msg)
        return
    save_state(st)


if __name__ == '__main__':
    main()
