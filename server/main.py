import os

from dotenv import load_dotenv

# Must run before the imports below: they read their configuration (DATABASE_URL,
# RECEIVE_DIR, LLM_API_KEY) on import. Variables already in the real
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

import llm.llm as llm
from llm.roomDescription import Anchor, Room, Payload, describe_room
from llm.determine_problems import determine_problems, CompanyNotFound
from llm.conclusion import conclusion
from database import categories, get_db, init_db, models, schemas


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

RECEIVE_DIR = os.getenv("RECEIVE_DIR", "/var/www/webapp-bernhackt/received")
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

    try:
        description = await describe_room(payload.room, payload.captures, batch_dir)
        with open(f"{batch_dir}/description.json", "w") as f:
            json.dump(description, f, indent=2)

        print(f"[{stamp}] {len(payload.room.anchors)} anchors, {len(payload.captures)} images saved to {batch_dir}")

        problems = await determine_problems(json.dumps(description), payload.company_name)
        plan = await conclusion(payload.room.model_dump(), problems)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CompanyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except llm.LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    with open(f"{batch_dir}/problems.txt", "w") as f:
        f.write(problems)
    with open(f"{batch_dir}/plan.json", "w") as f:
        json.dump(plan, f, indent=2)

    return {
        "status": "ok",
        "batch": stamp,
        "received_images": len(payload.captures),
        "description": description,
        "problems": problems,
        "plan": plan,
    }


# --- gemini -----------------------------------------------------------------

class GeminiRequest(BaseModel):
    prompt: str
    # Raw base64 JPEGs, same encoding the VR app posts to /receive-data.
    images: List[str] = []
    # Overrides LLM_MODEL / the default model for this one request.
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
    """Send a prompt and any attached images to the model and return its answer."""
    try:
        output = await llm.generate(payload.prompt, payload.images, payload.model)
    except ValueError as exc:  # undecodable image: the caller's problem
        raise HTTPException(status_code=400, detail=str(exc))
    except llm.LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    print(f"[llm] prompt {len(payload.prompt)} chars, {len(payload.images)} images -> {len(output)} chars")
    return {"status": "ok", "output": output}


# --- stored gemini outputs --------------------------------------------------

# The name of every batch directory /receive-data writes, so it doubles as the
# batch's timestamp.
BATCH_STAMP_FORMAT = "%Y%m%d_%H%M%S"


class GeminiOutputOut(BaseModel):
    """One model answer that /receive-data already stored on disk."""

    batch: str
    created_at: datetime
    images: int
    anchors: int
    description: str


def _read_batch(batch: str) -> Optional[GeminiOutputOut]:
    """Load one stored batch, or None if it holds no model output (yet)."""
    batch_dir = os.path.join(RECEIVE_DIR, batch)
    description_path = os.path.join(batch_dir, "description.json")
    if not os.path.isfile(description_path):
        return None

    with open(description_path) as f:
        description = json.load(f).get("description", "")

    anchors = 0
    room_path = os.path.join(batch_dir, "room.json")
    if os.path.isfile(room_path):
        with open(room_path) as f:
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
    )


@app.get("/gemini-outputs", response_model=List[GeminiOutputOut])
async def list_gemini_outputs():
    """Every model answer stored under RECEIVE_DIR, newest batch first."""
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
    # The batch name goes straight into a path, so it may only be a plain
    # directory name -- never a way out of RECEIVE_DIR.
    if batch != os.path.basename(batch) or batch in ("", ".", ".."):
        raise HTTPException(status_code=400, detail=f"invalid batch {batch!r}")

    output = _read_batch(batch)
    if output is None:
        raise HTTPException(status_code=404, detail=f"no gemini output for batch {batch!r}")
    return output


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
