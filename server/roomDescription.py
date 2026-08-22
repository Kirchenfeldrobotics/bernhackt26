import os

from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List, Optional

from google import genai

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


def describe_room(room: Room, captures: List[str], batch_dir: str) -> dict:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    prompt = (
        f"Describe this scanned room based on the following anchors: "
        f"{[anchor.model_dump() for anchor in room.anchors]}. "
        f"{len(captures)} image(s) were also captured of the room."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    return {"description": response.text}
