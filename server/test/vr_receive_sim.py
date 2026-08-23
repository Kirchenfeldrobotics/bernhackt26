import base64
import json
import os

import httpx


API_URL = "https://bernhackt26.kirchenfeldrobotics.ch/receive-data"

# must already exist: post company_post_sim.py first
COMPANY_NAME = "3dMike"

HERE = os.path.dirname(os.path.abspath(__file__))

ROOM_JSON = os.path.join(HERE, "room.json")

IMAGES = [
    os.path.join(HERE, "img_00.jpg"),
    os.path.join(HERE, "img_01.jpg"),
]

TIMEOUT = 300


# same shape the app writes to room.json, so a real capture can be replayed
with open(ROOM_JSON) as f:
    room = json.load(f)

if "room" in room:
    room = room["room"]

# the headset sends jpegs as raw base64, no data-url prefix
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
