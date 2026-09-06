#!/usr/bin/env python3
"""Check whether a Yahoo page response is the league or the sign-in wall."""
import requests
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
h = requests.get("https://fantasysports.yahoo.com/football/league/968508/teams",
                 headers=UA, timeout=20).text
wall = ('Sign in' in h or 'signin' in h.lower()[:5000])
league = ('BEEF' in h or '968508' in h)
print('sign-in wall:', wall)
print('league content visible:', league)
print('title:', h[h.lower().find('<title>')+7:h.lower().find('</title>')] if '<title>' in h.lower() else '?')
# where does it redirect?
r = requests.get("https://fantasysports.yahoo.com/football/league/968508/teams",
                 headers=UA, timeout=20, allow_redirects=False)
print('status:', r.status_code, '| location:', r.headers.get('location', 'none')[:100])
