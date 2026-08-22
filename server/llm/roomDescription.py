from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List, Optional

import llm.gemini as gemini
from llm.objects import OBJECT_TYPES as Object

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
        f"""I did an VR scan. Help me get the coordinates of the following targets: {Object.TRASHES}. They are contained in the following images: {len(captures)} inside this room/workspace.
        For coordination references, you will have these anchors that were identified, with coordinates and names, please use these referential positions to help identify your target's position based on your estimation of distance. Anchors: {[anchor.model_dump() for anchor in room.anchors]}.
        Observations:
        - If there is one or more target you must answer \"||:;X=0, Y=0, Z=0, {Object.TRASHES};:||\"
        - If there is not a single target in all the images you must reply with \"None {Object.TRASHES} detected\"
        - The only answers and words you can give are those 2 observations above you, do not drop free words before or after them."""
    )

    text = await gemini.generate(prompt, images=captures)

    return {"description": text}
