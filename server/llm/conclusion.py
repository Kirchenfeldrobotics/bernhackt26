"""Step 3 of the analysis pipeline: turn problems into placed, costed, real-product
conclusions.

Takes the problem list determine_problems() produced plus the MRUK anchors the
Meta Quest scanned, and asks the model for concrete, real-product fixes -- each one
pinned to a spot in the room so the VR app knows where to show it.

    plan = await conclusion(payload.room.model_dump(), problems)
    for c in plan["conclusions"]:
        print(c["product_name"], c["position"], c["savings_10y_chf"])

Grounding: none. Live web search was a provider-specific feature of the old
Gemini SDK and has no equivalent in the OpenAI chat-completions API, so
`_research()` now runs on the model's own knowledge. The two-call structure is
kept so real search can be reattached per provider later:

1. `_research()` -- schema-free, asking the model for real, currently
   purchasable products for the problems at hand, reported as plain text and
   including a source URL only where it is genuinely sure of one.
2. `conclusion()`'s main call -- schema-constrained, no tools, that folds that
   research text (plus the problems and anchors) into the final ConclusionPlan.

`product_url` stays optional: search does not always turn up a clean source link,
and the second call is told not to invent one when the research did not supply it.
"""
import json
from typing import Any, Optional

from pydantic import BaseModel, Field

import llm.llm as llm

# Keeps one runaway answer from filling the room with panels.
MAX_CONCLUSIONS = 8


class Position(BaseModel):
    """A point in the same world space the MRUK anchors use, in metres."""

    x: float
    y: float
    z: float


class Conclusion(BaseModel):
    """One green fix, ready to be shown on a panel in the VR app.

    Field order is deliberate: the model fills a JSON schema top to bottom, so the
    reasoning (which problem, which product, why it fits) is settled before it
    commits to a number and a place.
    """

    problem: str = Field(
        description="Which problem from the list above this addresses, copied or "
        "closely paraphrased so it stays traceable back to it."
    )
    solution: str = Field(
        description="How the product below fixes that problem, one or two sentences."
    )
    title: str = Field(description="Short, concrete name of the fix. At most six words.")
    product_name: str = Field(description="Name of the real product or service being recommended.")
    product_details: str = Field(
        description="What it is, how it would be used in this room, and why it fits -- a "
        "few concrete sentences, not marketing copy."
    )
    product_url: Optional[str] = Field(
        default=None,
        description="A source link for the product, if the research below found one. "
        "Leave unset rather than guessing one.",
    )
    bullets: list[str] = Field(
        description="Two to four punchy bullet points describing the solution. "
        "At most ten words each, concrete and satisfying to read, no filler."
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

For up to {max_conclusions} of the most worthwhile problems, find one concrete,
real product or service each and report:

- which problem it addresses
- its real name, and a source URL if you found one
- what it is and why it fits this room
- a realistic ten-year CHF saving estimate and the one-line assumption behind it
- which anchor in the list above it belongs near

Prefer cheap, fast, obviously worthwhile changes over ambitious projects. Merge
duplicates -- one product per distinct fix. If a problem does not support a real,
findable product, say so plainly and skip it rather than inventing one.

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

- Each conclusion must address at least one of the problems listed above. Do not
  invent new problems.
- Ground each conclusion in the research above where it found a real, fitting
  product. Where the research did not turn up a good match for a problem worth
  fixing, use your own knowledge of a real product instead rather than skipping
  it, but never invent a URL -- leave `product_url` unset if you don't have one.
- Only things that can be done inside this room: bought, brought in, swapped,
  switched off, unplugged, rearranged or added by the people who work there.
  Nothing that needs renovation, moving building, or changing the business.
- Prefer cheap, fast, obviously worthwhile changes over ambitious projects.
- Then decide where each conclusion belongs in the room. Pick the anchor it
  relates to, and place the explanation panel just in front of or above that
  anchor -- somewhere a person standing in the room could read it. Never place a
  panel inside a wall, inside furniture, at floor level, or far from any anchor.
- Merge duplicates. One panel per distinct fix, at most {max_conclusions}, most
  worthwhile first.

## Step 2 -- answer

Return only JSON in the required schema, filled in as follows:

- `problem`: the problem this fixes, copied or closely paraphrased from above.
- `solution`: one or two sentences on how the product fixes it.
- `title`: the fix, named in at most six words.
- `product_name`: the real product or service's name.
- `product_details`: what it is, how it's used here, and why it fits -- concrete,
  not marketing copy.
- `product_url`: a source link, only if the research above gave you one.
- `bullets`: two to four bullets, at most ten words each. Punchy and rewarding
  to read: concrete actions and numbers, present tense, no filler words, no
  full sentences. This is the text a person sees first in VR.
- `savings_10y_chf`: money saved or earned over ten years, in Swiss francs, as a
  positive number. Be realistic for an office of this size -- a plausible small
  number beats an impressive invented one.
- `savings_basis`: the one-line assumption your number rests on.
- `anchor_label`: copy one label exactly as written in the anchor list above.
- `position`: x, y, z in metres, in the same coordinate space as the anchors,
  near the anchor you named.
- `placement_reasoning`: one line on why the panel goes exactly there.

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

    Makes two model calls -- one to research real products, then a
    schema-constrained call that structures the result (see the module
    docstring).

    Returns {"conclusions": [...]}, already parsed and validated against the
    schema. Raises ValueError on unusable input and llm.LLMError if either
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
    research = await llm.generate(research_prompt)

    prompt = PROMPT_TEMPLATE.format(
        problems=problems,
        anchors_json=anchors_text,
        research=research.strip(),
        max_conclusions=MAX_CONCLUSIONS,
    )

    # The schema is enforced while the answer is decoded, so the two steps above
    # happen in the model's thinking and only the JSON comes back.
    data = await llm.generate_json(prompt, ConclusionPlan)

    try:
        plan = ConclusionPlan.model_validate(data)
    except ValueError as exc:
        raise llm.LLMError(f"the model's JSON did not fit the schema: {exc}") from exc

    print(f"[conclusion] {anchor_count} anchors, {len(problems)} chars of problems, "
          f"{len(research)} chars researched -> {len(plan.conclusions)} conclusions")
    return plan.model_dump()
