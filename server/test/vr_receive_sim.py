"""Pretend to be the Meta Quest: POST a room scan to /receive-data.

Testing only. Point the variables below at a room JSON and some JPEGs, start
the server, and run it:

    python test/vr_receive_sim.py

The room JSON is the same shape the app writes to room.json in a batch dir,
so a previous capture can simply be replayed.
"""
import base64
import json
import os

import httpx

# --- what to send -----------------------------------------------------------

API_URL = "https://bernhackt26.kirchenfeldrobotics.ch/receive-data"

# Must already exist in the database -- see test/company_post_sim.py.
COMPANY_NAME = "3dMike"

HERE = os.path.dirname(os.path.abspath(__file__))

# Anchors: {"anchors": [{"label", "position", "rotation", "size"}, ...]}
ROOM_JSON = os.path.join(HERE, "room.json")

IMAGES = [
    os.path.join(HERE, "img_00.jpg"),
    os.path.join(HERE, "img_01.jpg"),
]

# describe_room() calls the model before answering, so this is not quick.
TIMEOUT = 300

# --- go ---------------------------------------------------------------------

with open(ROOM_JSON) as f:
    room = json.load(f)

# Accept a whole payload file too, not just the room part.
if "room" in room:
    room = room["room"]

captures = []
for path in IMAGES:
    with open(path, "rb") as f:
        captures.append(base64.b64encode(f.read()).decode())

payload = {"room": room, "captures": captures, "company_name": COMPANY_NAME}

print(f"POST {API_URL}")
print(f"  company {COMPANY_NAME}")
print(f"  {len(room.get('anchors', []))} anchors from {ROOM_JSON}")
for path, b64 in zip(IMAGES, captures):
    print(f"  {os.path.basename(path)}: {len(b64)} chars of base64")

response = httpx.post(API_URL, json=payload, timeout=TIMEOUT)

print(f"\n{response.status_code}")
try:
    print(json.dumps(response.json(), indent=2)[:4000])
except ValueError:
    print(response.text[:4000])
