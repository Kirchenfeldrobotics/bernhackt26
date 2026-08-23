"""Accept one conclusion by id, the way the headset does.

    python test/accept_solution_sim.py <conclusion-id> [more ids...]

A conclusion is the unit that gets accepted: its problem, every solution
proposed for it and what they save are one panel in VR and one card in the web
app. The solutions inside it are that conclusion's detail and carry no ids.

/receive-data returns the ids it just stored, under "conclusions". To list what
is already in the database:

    sqlite3 -header -box "file:server/data/app.db?mode=ro" \
      "SELECT id, status, title FROM conclusions;"

Accepting the same conclusion twice is a no-op, so re-running this is harmless.
Pass --undo to hand the ids to /delete-solution instead.
"""

import json
import sys

import httpx

API_ROOT = "https://bernhackt26.kirchenfeldrobotics.ch"

TIMEOUT = 30


args = [a for a in sys.argv[1:] if a != "--undo"]
undo = "--undo" in sys.argv[1:]

if not args:
    print(__doc__)
    raise SystemExit(2)

failures = []

for conclusion_id in args:
    if undo:
        url = f"{API_ROOT}/delete-solution/{conclusion_id}"
        print(f"DELETE {url}")
        response = httpx.delete(url, timeout=TIMEOUT)
    else:
        url = f"{API_ROOT}/accept-solution"
        print(f"POST {url}")
        print(f"  conclusion_id {conclusion_id}")
        response = httpx.post(url, json={"conclusion_id": conclusion_id}, timeout=TIMEOUT)

    print(f"  {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        print(f"  {response.text[:300]}")
        failures.append(conclusion_id)
        print()
        continue

    # both routes answer with the whole conclusion, so its new status is visible
    if response.status_code == 200:
        print(f"  {body.get('title')!r} -> status {body.get('status')}")
        print(f"  {len(body.get('solutions') or [])} solution(s) inside it")
    else:
        # 404 means no conclusion carries that id -- usually stale or mistyped
        print(f"  {json.dumps(body)}")
        failures.append(conclusion_id)
    print()

print(f"{len(failures)} of {len(args)} failed" if failures else f"all {len(args)} ok")
raise SystemExit(1 if failures else 0)
