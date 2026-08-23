"""Step 2 of the analysis pipeline: turn problems into placed, costed solutions.

Takes the problem list determine_problems() produced plus the MRUK anchors the
Meta Quest scanned, and asks Gemini for concrete fixes -- each one pinned to a
spot in the room so the VR app knows where to show it.

What comes back is the *conclusion*: one entry per fix, carrying the five things
the web app lists, in this order.

    1. title      -- what the fix is
    2. problem    -- the negative impact it removes
    3. solutions  -- how to do it
    4. products   -- what to buy and where; null until a catalogue fills it in
    5. savings    -- what the company earns by doing it

Use:

    conclusion = await solutions(payload.room.model_dump(), problems)
    for entry in conclusion["entries"]:
        print(entry["title"], entry["position"], entry["savings_10y_chf"])
"""
import json
from typing import Any, Optional

from pydantic import BaseModel, Field

import llm.gemini as gemini

# Keeps one runaway answer from filling the room with panels.
MAX_SOLUTIONS = 8


class Position(BaseModel):
    """A point in the same world space the MRUK anchors use, in metres."""

    x: float
    y: float
    z: float


class Product(BaseModel):
    """Something to buy for a solution, and the page it can be bought on."""

    name: str
    url: str


class Solution(BaseModel):
    """One conclusion entry, as Gemini fills it in.

    Field order is deliberate: Gemini fills a JSON schema top to bottom, so the
    reasoning -- what is wrong, then what to do about it -- is settled before it
    commits to a number and a place.

    `products` is deliberately not here; see ConclusionEntry.
    """

    title: str = Field(description="Short, concrete name of the fix. At most six words.")
    problem: str = Field(
        description="The negative impact this fix removes: the problem from the list "
        "given, in one or two sentences. State only what is wrong, never how to fix "
        "it -- the fields below are for that."
    )
    solutions: list[str] = Field(
        description="Two to four punchy bullet points describing what to do. "
        "At most ten words each, concrete and satisfying to read, no filler."
    )
    benefit: str = Field(
        description="What the company gets out of doing this: environmental and "
        "operational impact, one or two sentences."
    )
    savings_10y_chf: float = Field(
        description="Money saved or earned over the next ten years in Swiss francs, "
        "cumulative and positive."
    )
    savings_basis: str = Field(
        description="The assumption behind that number, in one line, so it can be checked."
    )
    anchor_label: str = Field(
        description="Label of the MRUK anchor this solution belongs to. Must be one "
        "of the labels given in the anchor list."
    )
    position: Position = Field(
        description="Where the explanation panel floats, in the anchors' coordinate space."
    )
    placement_reasoning: str = Field(
        description="One line on why the panel goes there, referring to the anchor used."
    )


class ConclusionEntry(Solution):
    """A solution as it leaves the server, with the product slot added.

    Products stay out of the schema Gemini answers with: it has no catalogue, so
    anything it wrote there would be an invented shop URL. The field is null
    until a real product source fills it in, and the web app reads null as "not
    sourced yet" rather than "none needed".

    Inherited fields keep their order and `products` lands after them in the
    JSON; the display order is the one this module documents.
    """

    products: Optional[list[Product]] = None


class SolutionPlan(BaseModel):
    """The schema Gemini answers with: every solution found for this room."""

    entries: list[Solution]


class Conclusion(BaseModel):
    """The finished analysis, as the API serves it and the web app lists it."""

    entries: list[ConclusionEntry]


PROMPT_TEMPLATE = """\
You are designing a set of green improvements for one company's office, to be
presented to the staff inside a VR app that overlays them on the real room.

## Problems already found in this office

{problems}

## The room, as scanned by a Meta Quest

These are the MRUK anchors: real furniture and surfaces the headset detected.
`position` is [x, y, z] in metres in the room's world space, `rotation` is the
anchor's orientation, and `size` its extent where known. This is the only map of
the room you have.

{anchors_json}

## Step 1 -- think it through before you answer

Work out, for the problems above, the concrete fixes that are actually easy to
realise:

- Each solution must address at least one of the problems listed above. Do not
  invent new problems.
- Only things that can be done inside this room: bought, brought in, swapped,
  switched off, unplugged, rearranged or added by the people who work there.
  Nothing that needs renovation, moving building, or changing the business.
- Prefer cheap, fast, obviously worthwhile changes over ambitious projects.
- Then decide where each solution belongs in the room. Pick the anchor it
  relates to, and place the explanation panel just in front of or above that
  anchor -- somewhere a person standing in the room could read it. Never place a
  panel inside a wall, inside furniture, at floor level, or far from any anchor.
- Merge duplicates. One panel per distinct fix, at most {max_solutions}, most
  worthwhile first.

## Step 2 -- answer

Return only JSON in the required schema. Fill each entry in as follows:

- `title`: the fix, named in at most six words.
- `problem`: the negative impact this fix removes, in one or two sentences,
  taken from the problem list above. The problem only -- no fix, no "should",
  no "could be replaced by".
- `solutions`: two to four bullets, at most ten words each. Punchy and rewarding
  to read: concrete actions and numbers, present tense, no filler words, no
  full sentences. This is the text a person sees first in VR.
- `benefit`: one or two sentences on what the company gains, environmentally and
  practically.
- `savings_10y_chf`: money saved or earned over ten years, in Swiss francs, as a
  positive number. Be realistic for an office of this size -- a plausible small
  number beats an impressive invented one.
- `savings_basis`: the one-line assumption your number rests on.
- `anchor_label`: copy one label exactly as written in the anchor list above.
- `position`: x, y, z in metres, in the same coordinate space as the anchors,
  near the anchor you named.
- `placement_reasoning`: one line on why the panel goes exactly there.

Every entry must be grounded in the problems and the anchors given. If the
problems support fewer than {max_solutions} good solutions, return fewer.
"""


def _normalise_anchors(anchors_json: Any) -> tuple[str, int]:
    """Accept the anchors as JSON text, a dict, a list or a pydantic Room.

    Returns them pretty-printed for the prompt, plus how many there are.
    """
    if isinstance(anchors_json, str):
        try:
            data = json.loads(anchors_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"anchors_json is not valid JSON: {exc}") from exc
    elif isinstance(anchors_json, BaseModel):
        data = anchors_json.model_dump()
    else:
        data = anchors_json

    # Either the whole room object ({"anchors": [...]}) or the bare list.
    anchors = data.get("anchors") if isinstance(data, dict) else data
    if not isinstance(anchors, list) or not anchors:
        raise ValueError("anchors_json must contain at least one anchor")

    return json.dumps(anchors, indent=2, default=str), len(anchors)


def build_prompt(anchors_json: Any, problems: str) -> str:
    """Fill the solution prompt with one room's anchors and its problems."""
    anchors_text, _ = _normalise_anchors(anchors_json)
    return PROMPT_TEMPLATE.format(
        problems=problems.strip(),
        anchors_json=anchors_text,
        max_solutions=MAX_SOLUTIONS,
    )


async def solutions(anchors_json: Any, problems: str) -> dict:
    """Find green solutions for an office and pin each one to a spot in the room.

    `anchors_json` is the MRUK anchor data from the headset (JSON text, a dict, a
    list or a Room model); `problems` is the text determine_problems() returned.

    Returns {"entries": [...]}, already parsed and validated against the schema,
    every entry's `products` still null. Raises ValueError on unusable input and
    gemini.GeminiError if the model cannot be reached or answers with something
    the schema rejects.
    """
    problems = problems.strip()
    if not problems:
        raise ValueError("problems must not be empty")

    anchors_text, anchor_count = _normalise_anchors(anchors_json)
    prompt = PROMPT_TEMPLATE.format(
        problems=problems,
        anchors_json=anchors_text,
        max_solutions=MAX_SOLUTIONS,
    )

    # The schema is enforced while the answer is decoded, so the two steps above
    # happen in the model's thinking and only the JSON comes back.
    data = await gemini.generate_json(prompt, SolutionPlan)

    try:
        plan = SolutionPlan.model_validate(data)
    except ValueError as exc:
        raise gemini.GeminiError(f"Gemini's JSON did not fit the schema: {exc}") from exc

    conclusion = Conclusion(
        entries=[ConclusionEntry(**entry.model_dump()) for entry in plan.entries]
    )

    print(f"[solutions] {anchor_count} anchors, {len(problems)} chars of problems "
          f"-> {len(conclusion.entries)} entries")
    return conclusion.model_dump()
