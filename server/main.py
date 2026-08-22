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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional
import base64
import json
from datetime import datetime

import llm.gemini as gemini
from llm.roomDescription import Anchor, Room, Payload, describe_room
from llm.determine_problems import determine_problems, CompanyNotFound
from llm.conclusion import conclusion
from database import get_db, init_db, models, persistence, schemas


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

RECEIVE_DIR = os.getenv("RECEIVE_DIR", "/var/www/webapp-bernhackt/server/received")
os.makedirs(RECEIVE_DIR, exist_ok=True)

@app.get("/")
async def root():
    return {"status": "alive"}

@app.post("/receive-data")
async def receive_data(payload: Payload, db: Session = Depends(get_db)):
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
    except gemini.GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except gemini.GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    with open(f"{batch_dir}/problems.txt", "w") as f:
        f.write(problems)
    try:
        # Also stamps a uuid onto every solution in `plan`, so do this before
        # the plan is written out or returned.
        persistence.save_plan(plan, payload.company_name, stamp, db)
    except Exception as exc:  # Gemini already succeeded; do not lose that response.
        print(f"[{stamp}] failed to persist conclusions to the database: {exc}")

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



# --- stored gemini outputs --------------------------------------------------

# The name of every batch directory /receive-data writes, so it doubles as the
# batch's timestamp.
BATCH_STAMP_FORMAT = "%Y%m%d_%H%M%S"


class GeminiOutputOut(BaseModel):
    """One Gemini answer that /receive-data already stored on disk."""

    batch: str
    created_at: datetime
    images: int
    anchors: int
    description: str


def _read_batch(batch: str) -> Optional[GeminiOutputOut]:
    """Load one stored batch, or None if it holds no Gemini output (yet)."""
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
    # The batch name goes straight into a path, so it may only be a plain
    # directory name -- never a way out of RECEIVE_DIR.
    if batch != os.path.basename(batch) or batch in ("", ".", ".."):
        raise HTTPException(status_code=400, detail=f"invalid batch {batch!r}")

    output = _read_batch(batch)
    if output is None:
        raise HTTPException(status_code=404, detail=f"no gemini output for batch {batch!r}")
    return output


# --- companies --------------------------------------------------------------

@app.get("/companies", response_model=List[schemas.CompanyOut])
async def list_companies(db: Session = Depends(get_db)):
    return db.scalars(select(models.Company).order_by(models.Company.name)).all()


@app.get("/companies/{name}", response_model=schemas.CompanyOut)
async def get_company(name: str, db: Session = Depends(get_db)):
    company = db.scalar(select(models.Company).where(models.Company.name == name))
    if company is None:
        raise HTTPException(status_code=404, detail=f"no company named {name!r}")
    return company


@app.post("/companies", response_model=schemas.CompanyOut)
async def upsert_company(payload: schemas.CompanyIn, db: Session = Depends(get_db)):
    """Create the company, or update its details if it already exists."""
    company = db.scalar(select(models.Company).where(models.Company.name == payload.name))
    if company is None:
        company = models.Company(
            name=payload.name,
            website=payload.website,
            details=payload.details,
        )
        db.add(company)
    else:
        if payload.website is not None:
            company.website = payload.website
        if payload.details is not None:
            company.details = payload.details
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


# --- accepted solutions -----------------------------------------------------

@app.post("/accept-solution")
async def accept_solution(payload: schemas.AcceptedSolutionIn, db: Session = Depends(get_db)):
    """Record a solution the user accepted in VR.

    Accepting the same uuid again is a no-op, so a headset on a flaky link can
    retry without the second attempt looking like a failure.
    """
    if db.get(models.AcceptedSolution, payload.solution_uuid) is None:
        db.add(models.AcceptedSolution(solution_uuid=payload.solution_uuid))
        try:
            db.commit()
        except IntegrityError:
            # Another request accepted the same uuid in between. Still fine.
            db.rollback()

    return {"status": "ok", "solution_uuid": payload.solution_uuid}


@app.delete("/delete-solution/{solution_uuid}")
async def delete_solution(solution_uuid: str, db: Session = Depends(get_db)):
    """Drop a solution from the accepted list."""
    accepted = db.get(models.AcceptedSolution, solution_uuid)
    if accepted is None:
        raise HTTPException(status_code=404, detail=f"solution {solution_uuid!r} was not accepted")
    db.delete(accepted)
    db.commit()
    return {"status": "deleted", "solution_uuid": solution_uuid}


@app.post("/get-accepted-solutions", response_model=List[schemas.AcceptedSolutionOut])
async def get_accepted_solutions(payload: schemas.CompanyNameIn, db: Session = Depends(get_db)):
    """Every solution this company has accepted, with the conclusion around it.

    Solutions live inside each conclusion's JSON column rather than in a table
    of their own, so the mapping is: collect the company's solution ids, ask the
    database which of them were accepted, then keep those.
    """
    conclusions = db.scalars(
        select(models.Conclusion)
        .where(models.Conclusion.company_name == payload.company_name)
        .order_by(models.Conclusion.created_at, models.Conclusion.id)
    ).all()

    solution_ids = [
        solution["id"]
        for conclusion in conclusions
        for solution in conclusion.solutions or []
        if solution.get("id") is not None
    ]
    if not solution_ids:
        return []

    accepted = set(
        db.scalars(
            select(models.AcceptedSolution.solution_uuid).where(
                models.AcceptedSolution.solution_uuid.in_(solution_ids)
            )
        ).all()
    )

    return [
        schemas.AcceptedSolutionOut(
            solution=solution,
            conclusion=schemas.AcceptedSolutionConclusion.model_validate(conclusion),
        )
        for conclusion in conclusions
        for solution in conclusion.solutions or []
        if solution.get("id") in accepted
    ]
