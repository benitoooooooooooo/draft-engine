#!/usr/bin/env python3
"""Shared Yahoo Fantasy session for scripts + browser agent.

Single source of truth for the persistent, logged-in Chrome profile used to
drive league 968508. The same profile dir is passed to the Hermes browser
tool's Chrome launch, so a human one-time login persists across automation
runs. Nothing here stores credentials — Yahoo cookies live in the Chrome
profile only.

Conventions:
  profile dir : ~/yahoo-bot/chrome-profile   (chmod 700)
  league id   : ~/yahoo-bot/config.json
  headless CDP: scripts start chrome with --remote-debugging-port=9333
"""
import json
import os
import subprocess
import time

BASE = os.path.expanduser('~/yahoo-bot')
PROFILE = os.path.join(BASE, 'chrome-profile')
CONFIG_PATH = os.path.join(BASE, 'config.json')
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
CDP_PORT = 9333
LEAGUE_URL = "https://football.fantasysports.yahoo.com/f1/{}/teams"


def ensure_dirs():
    os.makedirs(PROFILE, exist_ok=True)
    os.chmod(BASE, 0o700)
    os.chmod(PROFILE, 0o700)


def save_config(league_id, game_code='nfl'):
    ensure_dirs()
    with open(CONFIG_PATH, 'w') as f:
        json.dump({'league_id': str(league_id), 'game_code': game_code,
                   'profile': PROFILE, 'cdp_port': CDP_PORT}, f, indent=2)


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def launch_headless(headful=False):
    """Start Chrome on the persistent profile with CDP enabled (idempotent).

    A live instance is ONLY ever replaced when the caller explicitly wants
    headful and the running one is headless. Headless (script) callers must
    never kill a visible logged-in window — attaching over CDP is enough,
    and a kill races cookie flushes and can wipe a fresh login.
    """
    ensure_dirs()
    if chrome_alive():
        if not headful:
            return True  # scripts: use the running instance, any mode
        if not chrome_is_headless():
            return True  # user: the visible window they asked for exists
        # headful requested but a headless instance owns the profile
        subprocess.run(['pkill', '-f', PROFILE], check=False)
        for _ in range(40):
            if not chrome_alive():
                break
            time.sleep(0.25)
    args = [CHROME, f'--remote-debugging-port={CDP_PORT}',
            f'--user-data-dir={PROFILE}', '--no-first-run',
            '--no-default-browser-check', '--disable-background-timer-throttling',
            '--disable-extensions']
    if not headful:
        args += ['--headless=new', '--disable-gpu']
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if chrome_alive():
            return True
        time.sleep(0.25)
    return False


def chrome_alive():
    try:
        import urllib.request
        with urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json/version', timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def chrome_is_headless():
    """True if a headless Chrome is running on our profile.

    NOTE: Chrome >=132 headless=new self-reports as plain 'Chrome/...' on
    /json/version, so the CDP Browser string is NOT a reliable signal.
    Check the actual --headless=new process arg instead.
    """
    r = subprocess.run(['pgrep', '-f', PROFILE], capture_output=True, text=True)
    for pid in r.stdout.split():
        ps = subprocess.run(['ps', '-o', 'command=', '-p', pid],
                            capture_output=True, text=True).stdout
        if '--headless' in ps:
            return True
    return False


def league_page():
    c = load_config()
    return LEAGUE_URL.format(c['league_id'])


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'init':
        save_config(sys.argv[2] if len(sys.argv) > 2 else 968508)
        print('config written:', CONFIG_PATH)
    elif len(sys.argv) > 1 and sys.argv[1] == 'launch':
        headful = '--headful' in sys.argv
        ok = launch_headless(headful=headful)
        print('chrome up:', ok)
        if ok and headful and os.path.exists(CONFIG_PATH):
            # open the league page so the user lands on (or is bounced to) login
            import urllib.request
            url = league_page()
            try:
                req = urllib.request.Request(
                    f'http://127.0.0.1:{CDP_PORT}/json/new?{url}', method='PUT')
                urllib.request.urlopen(req, timeout=5)
                print('opened league page for sign-in:', url)
            except Exception as e:
                print('could not open tab:', e)
    else:
        print('chrome alive:', chrome_alive())
        print('league page:', league_page() if os.path.exists(CONFIG_PATH) else 'config missing')
