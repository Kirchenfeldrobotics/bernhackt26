import json
import re
from typing import Any, Optional

from google.genai import types
from pydantic import BaseModel, Field, field_validator

import llm.gemini as gemini

MAX_CONCLUSIONS = 8

SEARCH_TOOLS = [types.Tool(google_search=types.GoogleSearch())]


# a point in the anchors' world space, in metres
class Position(BaseModel):
    """A point in the same world space the MRUK anchors use, in metres."""

    x: float
    y: float
    z: float


# one fix for a problem, product or behavioural
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


# where a conclusion's panel floats in the room
class Anchor(BaseModel):
    """Where in the room a conclusion's explanation panel belongs."""

    label: str = Field(
        description="Label of the MRUK anchor this belongs to. Must be one of the "
        "labels given in the anchor list."
    )
    position: Position = Field(
        description="Where the explanation panel floats, in the anchors' coordinate space."
    )


# one problem and every fix found for it, as shown on a vr panel
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
        description="Exactly '|amount|explanation': a pipe, then the whole number of "
        "Swiss francs saved over ten years as digits only -- no currency symbol, no "
        "thousands separator, no decimals -- then a pipe, then one sentence saying "
        "where that figure comes from. Example: |1200|LED bulbs cut lighting use by "
        "about 70%."
    )
    anchor: Anchor = Field(
        description="Which MRUK anchor this belongs near, and where the panel floats."
    )

    # the model writes this as free text, so pin it to |amount|explanation before
    # it reaches the database, where it is one column
    @field_validator("savings_10y_chf", mode="before")
    @classmethod
    def normalise_savings(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("savings_10y_chf must be a string")

        # tolerate a missing leading pipe rather than failing a whole scan
        amount, separator, explanation = value.strip().lstrip("|").partition("|")
        if not separator:
            raise ValueError("savings_10y_chf must be '|amount|explanation'")

        # strip currency and thousands separators the prompt asked it to omit
        digits = re.search(r"\d+", amount.replace("'", "").replace(",", "").replace(" ", ""))
        explanation = explanation.strip()
        if digits is None or not explanation:
            raise ValueError(f"savings_10y_chf has no amount or no explanation: {value!r}")

        return f"|{int(digits.group())}|{explanation}"


# the whole structured answer stage three returns
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
- `savings_10y_chf`: exactly `|amount|explanation`, in three parts and nothing
  else:
  1. a leading pipe;
  2. the amount: the whole number of Swiss francs saved over ten years, written
     as digits only. No `CHF`, no `.-`, no thousands separator, no decimals;
  3. a second pipe, then one sentence saying where that figure comes from.

  Be realistic for an office of this size -- a plausible small number beats an
  impressive invented one. Never put a pipe anywhere else in the sentence.
  Correct: `|1200|LED bulbs cut lighting electricity use by roughly 70%.`
  Wrong: `1200 CHF`, `|CHF 1'200|...`, `|1200.00|...`, `1200|...`
- `anchor`: where the panel belongs --
  - `label`: copy one label exactly as written in the anchor list above.
  - `position`: x, y, z in metres, in the same coordinate space as the
    anchors, near the anchor you named.

Every conclusion must be grounded in the problems and the anchors given. If the
problems support fewer than {max_conclusions} good conclusions, return fewer.
"""


# callers pass anchors as text, a dict, a list or a Room; accept all four
def _normalise_anchors(anchors_json: Any) -> tuple[str, int]:
    if isinstance(anchors_json, str):
        try:
            data = json.loads(anchors_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"anchors_json is not valid JSON: {exc}") from exc
    elif isinstance(anchors_json, BaseModel):
        data = anchors_json.model_dump()
    else:
        data = anchors_json

    anchors = data.get("anchors") if isinstance(data, dict) else data
    if not isinstance(anchors, list) or not anchors:
        raise ValueError("anchors_json must contain at least one anchor")

    return json.dumps(anchors, indent=2, default=str), len(anchors)


# stage three: research real products for the problems, then place each fix in the room
async def conclusion(anchors_json: Any, problems: str) -> dict:
    problems = problems.strip()
    if not problems:
        raise ValueError("problems must not be empty")

    anchors_text, anchor_count = _normalise_anchors(anchors_json)

    research_prompt = RESEARCH_PROMPT_TEMPLATE.format(
        problems=problems,
        anchors_json=anchors_text,
        max_conclusions=MAX_CONCLUSIONS,
    )
    # grounded call first: search cannot be combined with a forced schema
    research = await gemini.generate(research_prompt, tools=SEARCH_TOOLS)

    prompt = PROMPT_TEMPLATE.format(
        problems=problems,
        anchors_json=anchors_text,
        research=research.strip(),
        max_conclusions=MAX_CONCLUSIONS,
    )

    # then a schema-locked call that folds the research into the final plan
    data = await gemini.generate_json(prompt, ConclusionPlan)

    try:
        plan = ConclusionPlan.model_validate(data)
    except ValueError as exc:
        raise gemini.GeminiError(f"Gemini's JSON did not fit the schema: {exc}") from exc

    print(f"[conclusion] {anchor_count} anchors, {len(problems)} chars of problems, "
          f"{len(research)} chars researched -> {len(plan.conclusions)} conclusions")
    return plan.model_dump()
