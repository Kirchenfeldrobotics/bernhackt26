from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List, Optional

import gemini
from Objects import OBJECT_TYPES as Object

load_dotenv()

__all__ = ["Anchor", "Room", "Payload", "describe_room"]


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


async def describe_room(room: Room, captures: List[str], batch_dir: str) -> dict:
    prompt = (
        f"""Help me get the coordinates of the following targets: {Object.TRASHES}. They are contained in the following images: {len(captures)} inside this room/workspace.
        For coordination references, you will have these anchors that were identified, with coordinates and names, please use these referential positions to help identify your target's position. Anchors: {[anchor.model_dump() for anchor in room.anchors]}.
        Observations:
        - If there is not any target in all the images you should just reply with \"None {Object.TRASHES} detected\""""
    )

    text = await gemini.generate(prompt, images=captures)

    return {"description": text}
