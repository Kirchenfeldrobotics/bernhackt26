from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List, Optional

import llm.gemini as gemini
from llm.objects import OBJECT_TYPES as Object

load_dotenv()

__all__ = ["Anchor", "DescribedAnchor", "Room", "RoomDescription", "Payload", "describe_room"]


class Anchor(BaseModel):
    label: str
    position: List[float]
    rotation: List[float]
    size: Optional[List[float]] = None


class DescribedAnchor(Anchor):
    """An Anchor plus what Gemini made of it (or of something it found on its own)."""

    details: str


class Room(BaseModel):
    anchors: List[Anchor]


class RoomDescription(BaseModel):
    """Every anchor Gemini was given, plus anything further it found in the images."""

    anchors: List[DescribedAnchor]


class Payload(BaseModel):
    room: Room
    captures: List[str]
    company_name: str


async def describe_room(room: Room, captures: List[str], batch_dir: str) -> dict:
    object_types = ", ".join(o.value for o in Object)
    anchors_json = [anchor.model_dump() for anchor in room.anchors]

    prompt = (
        f"""I did a VR scan. Help me build a full description of every object of interest inside this room/workspace, contained in the following images: {len(captures)}.
        For coordination references, you will have these anchors that were identified, with coordinates and names, please use these referential positions to help identify any object's position based on your estimation of distance. Anchors (Measurements in Meters): {anchors_json}.

        Return ONE unified list of objects, merging together:
        1. Every anchor listed above, copied back exactly as given (same label, position, rotation, size), each with a new "details" field: a plain-language explanation of what the object is, its apparent condition, and anything about it relevant to sustainability, inferred from the images.
        2. Any further objects you can find across all the images that are not already one of the anchors above, restricted to these types: {object_types}. For each one you find, estimate its position as "<your estimated X>, <your estimated Y>, <your estimated Z, up and down>", using the anchors as your distance and scale reference, give it the closest matching label from {object_types}, and add a "details" field the same way as above.

        Observations:
        - If there is not a single object of a given additional type in any of the images, do not add an entry for it -- do not invent one.
        - Every anchor from the list above must appear in your answer exactly once, even if all you can add about it is a plain description.
        - Position and rotation stay in Meters, in the same coordinate space as the anchors above."""
    )

    data = await gemini.generate_json(prompt, RoomDescription, images=captures)
    try:
        description = RoomDescription.model_validate(data)
    except ValueError as exc:
        raise gemini.GeminiError(f"Gemini's JSON did not fit the schema: {exc}") from exc

    print(f"[describe-room] {len(room.anchors)} input anchors, {len(captures)} images "
          f"-> {len(description.anchors)} anchors in description")
    return description.model_dump()
