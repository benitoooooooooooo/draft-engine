#!/usr/bin/env python3
"""Simulate a full 150-pick draft through the real CLI at max speed,
verifying coach_notes.txt keeps up. Worst-case stress: no 60s clock gaps."""
import subprocess, time, json, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

pool = json.load(open('data/draft_pool.json'))
skill = [p['name'] for p in pool]

# Build a pick sequence: each team picks something plausible per position need
# Round 14/15 are K/DST -> 'pass'
lines = []
idx = 0
for pick in range(1, 151):
    rnd = (pick - 1) // 10 + 1
    if rnd >= 14:
        lines.append('pass')
    else:
        lines.append('pick ' + skill[idx % len(skill)])
        idx += 1

t0 = time.time()
r = subprocess.run(['python3', 'src/draft_cli.py'], input='\n'.join(lines) + '\nq\n',
                   capture_output=True, text=True, timeout=300)
dt = time.time() - t0
ok = r.stdout.count('✓')
print(f"CLI processed {ok}/150 picks in {dt:.1f}s ({dt/150*1000:.0f} ms/pick incl. render)")
if r.returncode != 0:
    print('CLI stderr tail:', r.stderr[-500:])

# Wait for daemon to settle
time.sleep(1.5)
if os.path.exists('coach_notes.txt'):
    age = time.time() - os.path.getmtime('coach_notes.txt')
    print(f"coach_notes.txt last written {age:.1f}s ago")
if os.path.exists('coach_log.txt'):
    entries = open('coach_log.txt').read().count('BEEF draft')
    print(f"coach_log.txt entries: {entries} (one per pick event noticed)")
print('\n=== final notes ===')
print(open('coach_notes.txt').read())
