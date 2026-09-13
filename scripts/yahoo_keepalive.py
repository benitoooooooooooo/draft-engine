#!/usr/bin/env python3
"""KEEPALIVE (cron --no-agent on the mini). Touches the league once to roll
Yahoo's session-idle clock. Silent when healthy (no Telegram spam); prints an
ALERT line only when the session has actually died, so the failure surfaces
hours before a real job needs the login."""
import json
import subprocess
import sys

sys.path.insert(0, '/Users/benbrackett/draft-engine/scripts')
from yahoo_session import load_config, launch_headless
from optimize_lineup import BUN, EVAL, JS

PROBE = 'JSON.stringify({url: location.href, title: document.title})'


def main():
    cfg = load_config()
    launch_headless()
    lid = cfg['league_id']
    url = f'https://football.fantasysports.yahoo.com/f1/{lid}/4/starters'
    # one JS-free probe: final URL + title after redirect settles
    out = subprocess.run([BUN, EVAL, url, PROBE], capture_output=True,
                         text=True, timeout=120)
    lines = out.stdout.strip().splitlines()
    if not lines:
        print('ALERT: yahoo keepalive got no CDP response (chrome down on '
              'mini?). Re-login: ~/draft-engine/.venv/bin/python '
              '~/draft-engine/scripts/yahoo_session.py launch --headful')
        sys.exit(0)
    r = json.loads(lines[-1])
    r = json.loads(r) if isinstance(r, str) else r
    if 'login.yahoo.com' in r.get('url', '') or 'Login' in r.get('title', ''):
        print('ALERT: YAHOO SESSION EXPIRED (keepalive probe hit the login '
              'wall, and it died DESPITE the heartbeat — likely a fresh '
              'Yahoo login elsewhere revoked it). Re-login needed on the '
              'mini before the next card run.')
        sys.exit(0)
    # healthy: heartbeat done, say nothing (empty stdout -> no delivery)


if __name__ == '__main__':
    main()
