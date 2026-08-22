from fastapi import FastAPI
import base64
import json
import os
from datetime import datetime

from roomDescription import Anchor, Room, Payload, describe_room

app = FastAPI()

RECEIVE_DIR = "/var/www/bernhackt26/received"
os.makedirs(RECEIVE_DIR, exist_ok=True)

@app.get("/")
async def root():
    return {"status": "alive"}

@app.post("/receive-data")
async def receive_data(payload: Payload):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = os.path.join(RECEIVE_DIR, stamp)
    os.makedirs(batch_dir, exist_ok=True)

    for i, b64 in enumerate(payload.captures):
        with open(f"{batch_dir}/img_{i:02d}.jpg", "wb") as f:
            f.write(base64.b64decode(b64))

    with open(f"{batch_dir}/room.json", "w") as f:
        f.write(payload.room.model_dump_json(indent=2))

    description = describe_room(payload.room, payload.captures, batch_dir)
    with open(f"{batch_dir}/description.json", "w") as f:
        json.dump(description, f, indent=2)

    print(f"[{stamp}] {len(payload.room.anchors)} anchors, {len(payload.captures)} images saved to {batch_dir}")
    return {
        "status": "ok",
        "batch": stamp,
        "received_images": len(payload.captures),
        "description": description,
    }
