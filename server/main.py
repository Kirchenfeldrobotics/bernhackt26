from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import base64
import os
from datetime import datetime

app = FastAPI()

RECEIVE_DIR = "/var/www/bernhackt26/received"
os.makedirs(RECEIVE_DIR, exist_ok=True)

class Anchor(BaseModel):
    label: str
    position: List[float]
    rotation: List[float]
    size: Optional[List[float]] = None

class Room(BaseModel):
    anchors: List[Anchor]

class Payload(BaseModel):
    room: Room
    captures: List[str]

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

    print(f"[{stamp}] {len(payload.room.anchors)} anchors, {len(payload.captures)} images saved to {batch_dir}")
    return {"status": "ok", "batch": stamp, "received_images": len(payload.captures)}
