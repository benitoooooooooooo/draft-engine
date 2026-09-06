#!/usr/bin/env python3
"""LINEUP CARD (runs natively on the mini via cron --no-agent).
Prints today's proposed Straight to Jail lineup; empty stdout = silent,
nonzero rc = error text delivered. The agent submits only after user ✅
in reply — this job only PROPOSES."""
import subprocess
import sys

r = subprocess.run(
    ['/Users/benbrackett/draft-engine/.venv/bin/python',
     'scripts/optimize_lineup.py'],
    cwd='/Users/benbrackett/draft-engine',
    capture_output=True, text=True, timeout=180)
if r.returncode != 0 or not r.stdout.strip():
    print(f'⚠️ LINEUP JOB FAILED: {(r.stderr or "no output")[-250:]}\n'
          f'Likely Yahoo session expiry — re-login needed on the mini.')
    sys.exit(0)
print(r.stdout.strip())
print('\n(reply ✅ in Telegram to have the agent submit this lineup, '
      'or name edits first)')
