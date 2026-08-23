import os

from dotenv import load_dotenv

# Must run before the imports below: they read their configuration (DATABASE_URL,
# RECEIVE_DIR, GEMINI_API_KEY) on import. Variables already in the real
# environment win over the file.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List, Optional
import base64
import json
from datetime import datetime

import llm.gemini as gemini
from llm.roomDescription import Anchor, Room, Payload, describe_room
from database import categories, get_db, init_db, models, schemas
from determine_problems import CompanyNotFound, determine_problems
from solutions import ConclusionEntry
from solutions import solutions as find_solutions


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

# Browsers only talk to this API from an origin named here. The deployed web
# app is not on localhost, so set ALLOWED_ORIGINS (comma separated) in .env to
# whatever serves it; "*" allows any origin.
DEFAULT_ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

RECEIVE_DIR = os.getenv("RECEIVE_DIR", "/var/www/bernhackt26/received")
os.makedirs(RECEIVE_DIR, exist_ok=True)

@app.get("/")
async def root():
    return {"status": "alive"}

# Receive data from vr
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

    description = await describe_room(payload.room, payload.captures, batch_dir)
    with open(f"{batch_dir}/description.json", "w") as f:
        json.dump(description, f, indent=2)

    print(f"[{stamp}] {len(payload.room.anchors)} anchors, {len(payload.captures)} images saved to {batch_dir}")

    # Kick off agent pipline

    # Send data back to vr

    return {
        "status": "ok",
        "batch": stamp,
        "received_images": len(payload.captures),
        "description": description,
    }


# --- gemini -----------------------------------------------------------------

class GeminiRequest(BaseModel):
    prompt: str
    # Raw base64 JPEGs, same encoding the VR app posts to /receive-data.
    images: List[str] = []
    # Overrides GEMINI_MODEL / the default model for this one request.
    model: Optional[str] = None

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be empty")
        return v


@app.post("/send-to-gemini")
async def send_to_gemini(payload: GeminiRequest):
    """Send a prompt and any attached images to Gemini and return its answer."""
    try:
        output = await gemini.generate(payload.prompt, payload.images, payload.model)
    except ValueError as exc:  # undecodable image: the caller's problem
        raise HTTPException(status_code=400, detail=str(exc))
    except gemini.GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except gemini.GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    print(f"[gemini] prompt {len(payload.prompt)} chars, {len(payload.images)} images -> {len(output)} chars")
    return {"status": "ok", "output": output}


# --- stored gemini outputs --------------------------------------------------

# The name of every batch directory /receive-data writes, so it doubles as the
# batch's timestamp.
BATCH_STAMP_FORMAT = "%Y%m%d_%H%M%S"


class StoredConclusion(BaseModel):
    """The finished analysis for one batch, as it sits in its conclusion.json.

    `entries` is the list the web app renders: title, problem, solutions,
    products and savings, one entry per fix. `problems` is step 1's answer kept
    verbatim -- the markdown the entries were derived from, shown as the audit's
    working notes.
    """

    company: str
    created_at: datetime
    problems: str
    entries: List[ConclusionEntry]


class GeminiOutputOut(BaseModel):
    """One Gemini answer that /receive-data already stored on disk."""

    batch: str
    created_at: datetime
    images: int
    anchors: int
    description: str
    # Null until the analysis has been run for this batch.
    conclusion: Optional[StoredConclusion] = None


def _batch_dir(batch: str) -> str:
    """The directory of one batch.

    The name goes straight into a path, so it may only be a plain directory
    name -- never a way out of RECEIVE_DIR.
    """
    if batch != os.path.basename(batch) or batch in ("", ".", ".."):
        raise HTTPException(status_code=400, detail=f"invalid batch {batch!r}")
    return os.path.join(RECEIVE_DIR, batch)


def _read_conclusion(batch_dir: str) -> Optional[StoredConclusion]:
    """Load a batch's stored conclusion, or None if it has not been run yet."""
    path = os.path.join(batch_dir, "conclusion.json")
    if not os.path.isfile(path):
        return None

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    try:
        return StoredConclusion.model_validate(data)
    except ValueError as exc:
        # Written by an older shape of the pipeline. A batch showing up without
        # its conclusion beats a 500 on the whole list.
        print(f"[conclusion] ignoring unreadable {path}: {exc}")
        return None


def _read_batch(batch: str) -> Optional[GeminiOutputOut]:
    """Load one stored batch, or None if it holds no Gemini output (yet)."""
    batch_dir = os.path.join(RECEIVE_DIR, batch)
    description_path = os.path.join(batch_dir, "description.json")
    if not os.path.isfile(description_path):
        return None

    with open(description_path, encoding="utf-8") as f:
        description = json.load(f).get("description", "")

    anchors = 0
    room_path = os.path.join(batch_dir, "room.json")
    if os.path.isfile(room_path):
        with open(room_path, encoding="utf-8") as f:
            anchors = len(json.load(f).get("anchors", []))

    try:
        created_at = datetime.strptime(batch, BATCH_STAMP_FORMAT)
    except ValueError:  # a directory not named by receive_data
        created_at = datetime.fromtimestamp(os.path.getmtime(batch_dir))

    return GeminiOutputOut(
        batch=batch,
        created_at=created_at,
        images=len([n for n in os.listdir(batch_dir) if n.endswith(".jpg")]),
        anchors=anchors,
        description=description,
        conclusion=_read_conclusion(batch_dir),
    )


@app.get("/gemini-outputs", response_model=List[GeminiOutputOut])
async def list_gemini_outputs():
    """Every Gemini answer stored under RECEIVE_DIR, newest batch first."""
    outputs = []
    for name in sorted(os.listdir(RECEIVE_DIR), reverse=True):
        if not os.path.isdir(os.path.join(RECEIVE_DIR, name)):
            continue
        output = _read_batch(name)
        if output is not None:
            outputs.append(output)
    return outputs


@app.get("/gemini-outputs/{batch}", response_model=GeminiOutputOut)
async def get_gemini_output(batch: str):
    _batch_dir(batch)  # rejects a name that is not a plain directory
    output = _read_batch(batch)
    if output is None:
        raise HTTPException(status_code=404, detail=f"no gemini output for batch {batch!r}")
    return output


# --- the conclusion: problems turned into placed, costed solutions ----------

class ConclusionRequest(BaseModel):
    """Which company a scan is being analysed for."""

    company: str

    @field_validator("company")
    @classmethod
    def company_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("company must not be empty")
        return v


@app.get("/gemini-outputs/{batch}/conclusion", response_model=StoredConclusion)
async def get_conclusion(batch: str):
    conclusion = _read_conclusion(_batch_dir(batch))
    if conclusion is None:
        raise HTTPException(status_code=404, detail=f"no conclusion for batch {batch!r}")
    return conclusion


@app.post("/gemini-outputs/{batch}/conclusion", response_model=StoredConclusion)
async def create_conclusion(batch: str, payload: ConclusionRequest):
    """Run the analysis pipeline over a stored scan and keep what it concludes.

    Step 1 names the problems from the room description and the company's own
    business description; step 2 turns them into placed, costed solutions.
    Running it again replaces the batch's previous conclusion.
    """
    batch_dir = _batch_dir(batch)
    description_path = os.path.join(batch_dir, "description.json")
    room_path = os.path.join(batch_dir, "room.json")
    if not os.path.isfile(description_path) or not os.path.isfile(room_path):
        raise HTTPException(status_code=404, detail=f"batch {batch!r} has no stored scan")

    with open(description_path, encoding="utf-8") as f:
        description = json.load(f).get("description", "")
    with open(room_path, encoding="utf-8") as f:
        room = json.load(f)

    try:
        problems = await determine_problems(description, payload.company)
        entries = (await find_solutions(room, problems))["entries"]
    except CompanyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except gemini.GeminiNotConfigured as exc:  # before GeminiError: it is a subclass
        raise HTTPException(status_code=503, detail=str(exc))
    except gemini.GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:  # an empty description or a scan with no anchors
        raise HTTPException(status_code=400, detail=str(exc))

    conclusion = StoredConclusion(
        company=payload.company,
        created_at=datetime.now(),
        problems=problems,
        entries=entries,
    )
    with open(os.path.join(batch_dir, "conclusion.json"), "w", encoding="utf-8") as f:
        f.write(conclusion.model_dump_json(indent=2))

    print(f"[conclusion] {batch} for {payload.company}: {len(conclusion.entries)} entries")
    return conclusion


# --- companies & categories -------------------------------------------------

@app.get("/categories")
async def list_categories():
    return {"categories": categories.CATEGORIES}


@app.get("/companies", response_model=List[schemas.CompanyOut])
async def list_companies(
    category: Optional[str] = Query(None, description="filter by exact category"),
    uncategorized: bool = Query(False, description="only companies with no category yet"),
    db: Session = Depends(get_db),
):
    stmt = select(models.Company).order_by(models.Company.name)
    if uncategorized:
        stmt = stmt.where(models.Company.category.is_(None))
    elif category is not None:
        stmt = stmt.where(models.Company.category == category)
    return db.scalars(stmt).all()


@app.get("/companies/{name}", response_model=schemas.CompanyOut)
async def get_company(name: str, db: Session = Depends(get_db)):
    company = db.scalar(select(models.Company).where(models.Company.name == name))
    if company is None:
        raise HTTPException(status_code=404, detail=f"no company named {name!r}")
    return company


@app.post("/companies", response_model=schemas.CompanyOut)
async def upsert_company(payload: schemas.CompanyIn, db: Session = Depends(get_db)):
    """Create the company, or update its category if it already exists."""
    company = db.scalar(select(models.Company).where(models.Company.name == payload.name))
    if company is None:
        company = models.Company(
            name=payload.name,
            category=payload.category,
            website=payload.website,
            details=payload.details,
        )
        db.add(company)
    else:
        if payload.category is not None:
            company.category = payload.category
        if payload.website is not None:
            company.website = payload.website
        if payload.details is not None:
            company.details = payload.details
    db.commit()
    db.refresh(company)
    return company


@app.put("/companies/{name}/category", response_model=schemas.CompanyOut)
async def set_category(name: str, payload: schemas.CategoryIn, db: Session = Depends(get_db)):
    """Assign a category to a company, creating the company if it is new."""
    company = db.scalar(select(models.Company).where(models.Company.name == name))
    if company is None:
        company = models.Company(name=name)
        db.add(company)
    company.category = payload.category
    db.commit()
    db.refresh(company)
    return company


@app.delete("/companies/{name}")
async def delete_company(name: str, db: Session = Depends(get_db)):
    company = db.scalar(select(models.Company).where(models.Company.name == name))
    if company is None:
        raise HTTPException(status_code=404, detail=f"no company named {name!r}")
    db.delete(company)
    db.commit()
    return {"status": "deleted", "name": name}
