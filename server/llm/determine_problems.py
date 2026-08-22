"""Step 1 of the analysis pipeline: name the sustainability problems in a room.

Takes a room description plus a company name, looks the company's business
description up in the database, and asks Gemini what is wrong. Deliberately
problems only -- a later prompt turns this output into solutions.

    problems = await determine_problems(room_description, "Beispiel AG")
"""
from sqlalchemy import select

import llm.gemini as gemini
from database import SessionLocal, models
from llm.objects import OBJECT_TYPES as Object

# Stands in for a field the company row does not have filled in yet, so the
# prompt never contains a dangling "None".
UNKNOWN = "(not available)"

# Rendered once into the prompt so Gemini knows which objects a later stage can
# actually place a fix against, without being told every problem must use one.
KNOWN_OBJECT_TYPES = ", ".join(o.value for o in Object)

PROMPT_TEMPLATE = """\
You are a sustainability auditor inspecting the workspace of a single company.

## The company

Name: {company_name}
Category: {company_category}
Business description:
{business_description}

## The office space

{room_description}

## What this system can act on

A later stage in this pipeline can place a fix near these object types, if it
finds one in the room: {known_object_types}. Where a problem plausibly involves
one of them, mention it by name so it can be grounded to something concrete
later -- but do not force the connection. Most problems will have nothing to do
with this list, and that is fine.

## Your task

List the sustainability problems that are present in this office space, judging
only from the two descriptions above.

Follow these rules exactly:

1. Problems only. Do not suggest, hint at, or describe any solution, fix,
   improvement or recommendation. Another analysis handles those later; your
   output is its input. Never write "should", "could be replaced by" or similar.

2. Stay inside the room. Only report a problem if fixing it would plausibly be
   possible within this space, with things that could be brought into the room,
   swapped out, switched off or rearranged by the people working there. Ignore
   anything that would need moving to another building, renovating the
   structure, or changing the company's supply chain or business model.

3. Stay grounded. Every problem must trace back to something actually stated in
   the room or business description. Do not invent equipment, habits or
   materials that are not mentioned. If the descriptions are too thin to
   support any real finding, say so plainly and list only what they do support.

4. Sweep broadly, within those limits: energy use and lighting, heating,
   cooling and ventilation, water, waste and recycling, consumables and
   materials, equipment and electronics, everyday purchasing, and how the space
   itself is used.

## Output format

A numbered list, most significant problem first, at most 10 entries. For each:

**<short title>**
Observed: <the thing in the descriptions this comes from>
Problem: <why it is a sustainability problem, in two or three sentences>

Each entry must stand entirely on its own -- it will later be read in isolation,
so never refer to other entries or to this instruction text. Output the list and
nothing else: no preamble, no summary, no closing remarks.
"""


class CompanyNotFound(LookupError):
    """No company of that name is in the database."""


def build_prompt(room_description: str, company: models.Company) -> str:
    """Fill the audit prompt with one company's data and its room."""
    return PROMPT_TEMPLATE.format(
        company_name=company.name,
        company_category=company.category or UNKNOWN,
        business_description=company.details or UNKNOWN,
        room_description=room_description,
        known_object_types=KNOWN_OBJECT_TYPES,
    )


async def determine_problems(room_description: str, company_name: str) -> str:
    """Find the sustainability problems in a company's office space.

    Reads the company's business description from the database itself, so the
    caller only needs the two strings. Returns Gemini's problem list.

    Raises ValueError on empty input, CompanyNotFound if the name is unknown,
    and gemini.GeminiError if the model cannot be reached or says nothing.
    """
    room_description = room_description.strip()
    company_name = company_name.strip()
    if not room_description:
        raise ValueError("room_description must not be empty")
    if not company_name:
        raise ValueError("company_name must not be empty")

    # The prompt is built inside the session and the call made outside it, so no
    # database connection is held open across the slow request to Gemini.
    with SessionLocal() as db:
        company = db.scalar(select(models.Company).where(models.Company.name == company_name))
        if company is None:
            raise CompanyNotFound(f"no company named {company_name!r}")
        prompt = build_prompt(room_description, company)

    output = await gemini.generate(prompt)

    print(f"[determine-problems] {company_name}: {len(prompt)} chars in -> {len(output)} chars out")
    return output
