"""Step 3 of the analysis pipeline: turn problems into placed, costed, real-product
conclusions.

Takes the problem list determine_problems() produced plus the MRUK anchors the
Meta Quest scanned, and asks Gemini for concrete, real-product fixes -- each one
pinned to a spot in the room so the VR app knows where to show it.

    plan = await conclusion(payload.room.model_dump(), problems)
    for c in plan["conclusions"]:
        print(c["title"], c["anchor"]["position"], c["savings_10y_chf"])

The Gemini API does not accept a forced-JSON `response_schema` together with a
search `tools` grounding call in the same request -- see gemini.generate()'s
docstring. So this module makes two calls:

1. `_research()` -- schema-free, with the search tool switched on, asking Gemini
   to find real, currently purchasable products for the problems at hand and
   report what it found as plain text, including any source URLs.
2. `conclusion()`'s main call -- schema-constrained, no tools, that folds that
   research text (plus the problems and anchors) into the final ConclusionPlan.

`product_url` stays optional: search does not always turn up a clean source link,
and the second call is told not to invent one when the research did not supply it.
"""
import json
from typing import Any, Optional

from pydantic import BaseModel, Field
from google.genai import types

import llm.gemini as gemini

# Keeps one runaway answer from filling the room with panels.
MAX_CONCLUSIONS = 8

SEARCH_TOOLS = [types.Tool(google_search=types.GoogleSearch())]


class Position(BaseModel):
    """A point in the same world space the MRUK anchors use, in metres."""

    x: float
    y: float
    z: float


class Solution(BaseModel):
    """One fix for a problem -- usually a real product, sometimes a written one."""

    name: str = Field(
        description="Name of the real product or service, or, for a written/behavioural "
        "fix with no product behind it, a short description of the fix itself."
    )
    url: Optional[str] = Field(
        default=None,
        description="A source link for the product, if the research below found one. "
        "Leave unset rather than guessing one. Written/behavioural solutions always "
        "leave this unset.",
    )
    description: str = Field(
        description="How this fixes the problem -- a few concrete sentences, not "
        "marketing copy."
    )


class Anchor(BaseModel):
    """Where in the room a conclusion's explanation panel belongs."""

    label: str = Field(
        description="Label of the MRUK anchor this belongs to. Must be one of the "
        "labels given in the anchor list."
    )
    position: Position = Field(
        description="Where the explanation panel floats, in the anchors' coordinate space."
    )


class Conclusion(BaseModel):
    """One problem and every fix found for it, ready to be shown on a panel in the VR app.

    Field order is deliberate: Gemini fills a JSON schema top to bottom, so the
    reasoning (which problem, which products, why they fit) is settled before it
    commits to a number and a place.
    """

    title: str = Field(description="Short, concrete name of the fix. At most six words.")
    problem: str = Field(
        description="The problem, phrased to include the negative impact it has on the "
        "room or workspace -- not just what's wrong, but what it costs or harms "
        "(comfort, energy, health, productivity, etc)."
    )
    solutions: list[Solution] = Field(
        description="One or more fixes for this problem. Prefer real, currently "
        "purchasable products for most of them; a written/behavioural fix is fine "
        "when that suits the problem better."
    )
    savings_10y_chf: str = Field(
        description="Formatted exactly as '|amount|explanation': a pipe, the CHF amount "
        "saved over ten years, another pipe, then a one-line explanation of why that "
        "much is saved, with no separator before it."
    )
    anchor: Anchor = Field(
        description="Which MRUK anchor this belongs near, and where the panel floats."
    )


class ConclusionPlan(BaseModel):
    """The whole answer: every conclusion found for this room."""

    conclusions: list[Conclusion]


RESEARCH_PROMPT_TEMPLATE = """\
You are researching real, currently purchasable products and services to fix
sustainability problems in one company's office.

## Problems already found in this office

{problems}

## The room, as scanned by a Meta Quest

These are the MRUK anchors: real furniture and surfaces the headset detected.
`position` is [x, y, z] in metres in the room's world space, `rotation` is the
anchor's orientation, and `size` its extent where known. This is the only map of
the room you have.

{anchors_json}

## Your task

Use web search to find real products or services that fix these problems --
things that can be bought, brought in, swapped, switched off, unplugged,
rearranged or added by the people who work there. Nothing that needs renovation,
moving building, or changing the business.

For up to {max_conclusions} of the most worthwhile problems, find one or more
concrete fixes each and report:

- which problem it addresses
- its real name, and a source URL if you found one
- what it is and why it fits this room
- a realistic ten-year CHF saving estimate and the one-line assumption behind it
- which anchor in the list above it belongs near

Prefer real, currently purchasable products for most fixes. Where a written or
behavioural change fits a problem better than any product (e.g. "turn off idle
monitors"), report that instead rather than forcing a product onto it. A single
problem can have more than one worthwhile fix -- report each one you find.

Prefer cheap, fast, obviously worthwhile changes over ambitious projects. Merge
duplicates -- one fix per distinct idea. If a problem does not support a real,
findable product, say so plainly and offer a written fix instead rather than
inventing a product.

Write your findings as plain text, one product per paragraph. This is
intermediate research for another step to structure, not the final answer, so
include everything you found, including any source URLs.
"""

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

## Product research already done

{research}

## Step 1 -- think it through before you answer

Work out, for the problems above, the concrete fixes that are actually easy to
realise:

- Each conclusion must address exactly one of the problems listed above. Do not
  invent new problems. A problem may get more than one conclusion object only if
  its fixes genuinely don't belong on the same panel -- normally, group every
  fix for one problem into that one conclusion's `solutions` list instead.
- Give each conclusion one or more solutions. Prefer real, currently purchasable
  products, grounded in the research above where it found a good match. Where
  neither the research nor your own knowledge has a real product for a problem
  worth fixing, give a written/behavioural solution instead (e.g. "turn off idle
  monitors") rather than inventing a product. Never invent a URL -- leave a
  solution's `url` unset if you don't have one; written/behavioural solutions
  always leave it unset.
- Only things that can be done inside this room: bought, brought in, swapped,
  switched off, unplugged, rearranged or added by the people who work there.
  Nothing that needs renovation, moving building, or changing the business.
- Prefer cheap, fast, obviously worthwhile changes over ambitious projects.
- Then decide where each conclusion belongs in the room. Pick the anchor it
  relates to, and place the explanation panel just in front of or above that
  anchor -- somewhere a person standing in the room could read it. Never place a
  panel inside a wall, inside furniture, at floor level, or far from any anchor.
- Merge duplicates. One conclusion per distinct problem, at most
  {max_conclusions}, most worthwhile first.

## Step 2 -- answer

Return only JSON in the required schema, filled in as follows:

- `title`: the fix, named in at most six words.
- `problem`: the problem this fixes, phrased to include the negative impact it
  has on the room or workspace -- not just what's wrong, but what it costs or
  harms (comfort, energy, health, productivity, etc), copied or closely
  paraphrased from above.
- `solutions`: a list of one or more fixes for this problem, each with:
  - `name`: the real product or service's name, or, for a written/behavioural
    fix, a short description of the fix itself.
  - `url`: a source link, only if the research above gave you one for that
    product; unset for written/behavioural fixes.
  - `description`: how it fixes the problem -- a few concrete sentences, not
    marketing copy.
- `savings_10y_chf`: formatted exactly as `|amount|explanation` -- a pipe,
  the CHF amount saved over ten years as a positive number, another pipe, then
  a one-line explanation of why that much is saved, directly after with no
  separator. Be realistic for an office of this size -- a plausible small
  number beats an impressive invented one. Example:
  `|1200|Switching to LED bulbs cuts lighting electricity use by roughly 70%,
  saving an estimated 1200 CHF over ten years.`
- `anchor`: where the panel belongs --
  - `label`: copy one label exactly as written in the anchor list above.
  - `position`: x, y, z in metres, in the same coordinate space as the
    anchors, near the anchor you named.

Every conclusion must be grounded in the problems and the anchors given. If the
problems support fewer than {max_conclusions} good conclusions, return fewer.
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


def build_research_prompt(anchors_json: Any, problems: str) -> str:
    """Fill the web-research prompt with one room's anchors and its problems."""
    anchors_text, _ = _normalise_anchors(anchors_json)
    return RESEARCH_PROMPT_TEMPLATE.format(
        problems=problems.strip(),
        anchors_json=anchors_text,
        max_conclusions=MAX_CONCLUSIONS,
    )


def build_prompt(anchors_json: Any, problems: str, research: str) -> str:
    """Fill the final structuring prompt with the room, its problems and the research."""
    anchors_text, _ = _normalise_anchors(anchors_json)
    return PROMPT_TEMPLATE.format(
        problems=problems.strip(),
        anchors_json=anchors_text,
        research=research.strip(),
        max_conclusions=MAX_CONCLUSIONS,
    )


async def conclusion(anchors_json: Any, problems: str) -> dict:
    """Find real-product green fixes for an office and pin each one to a spot in the room.

    `anchors_json` is the MRUK anchor data from the headset (JSON text, a dict, a
    list or a Room model); `problems` is the text determine_problems() returned.

    Makes two Gemini calls -- an ungrounded search-tool call to research real
    products, then a schema-constrained call with no tools that structures the
    result -- because the Gemini API does not allow combining the two in one
    request (see the module docstring).

    Returns {"conclusions": [...]}, already parsed and validated against the
    schema. Raises ValueError on unusable input and gemini.GeminiError if either
    call cannot be reached or the final one answers with something the schema
    rejects.
    """
    problems = problems.strip()
    if not problems:
        raise ValueError("problems must not be empty")

    anchors_text, anchor_count = _normalise_anchors(anchors_json)

    research_prompt = RESEARCH_PROMPT_TEMPLATE.format(
        problems=problems,
        anchors_json=anchors_text,
        max_conclusions=MAX_CONCLUSIONS,
    )
    research = await gemini.generate(research_prompt, tools=SEARCH_TOOLS)

    prompt = PROMPT_TEMPLATE.format(
        problems=problems,
        anchors_json=anchors_text,
        research=research.strip(),
        max_conclusions=MAX_CONCLUSIONS,
    )

    # The schema is enforced while the answer is decoded, so the two steps above
    # happen in the model's thinking and only the JSON comes back.
    data = await gemini.generate_json(prompt, ConclusionPlan)

    try:
        plan = ConclusionPlan.model_validate(data)
    except ValueError as exc:
        raise gemini.GeminiError(f"Gemini's JSON did not fit the schema: {exc}") from exc

    print(f"[conclusion] {anchor_count} anchors, {len(problems)} chars of problems, "
          f"{len(research)} chars researched -> {len(plan.conclusions)} conclusions")
    return plan.model_dump()
