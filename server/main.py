import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import base64
import json
import traceback
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

import llm.gemini as gemini
from database import SessionLocal, get_db, init_db, models, persistence, schemas
from llm.conclusion import conclusion
from llm.determine_problems import CompanyNotFound, determine_problems
from llm.room_description import Payload, describe_room


# make the scan directory and tables before the first request lands
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    os.makedirs(RECEIVE_DIR, exist_ok=True)
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

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

BATCH_STAMP_FORMAT = "%Y%m%d_%H%M%S"


# claim a batch directory, suffixed when two scans land in the same second
def _make_batch_dir(receive_dir: str) -> tuple[str, str]:
    stamp = datetime.now().strftime(BATCH_STAMP_FORMAT)
    candidate = stamp
    attempt = 1
    while True:
        path = os.path.join(receive_dir, candidate)
        try:
            os.makedirs(path, exist_ok=False)
            return candidate, path
        except FileExistsError:
            attempt += 1
            candidate = f"{stamp}_{attempt}"


# decode and store the scan's jpegs, rejecting anything that is not base64
def _write_captures(batch_dir: str, captures: list[str]) -> None:
    for i, b64 in enumerate(captures):
        try:
            raw = base64.b64decode("".join(b64.split()), validate=True)
        except ValueError as exc:
            raise ValueError(f"capture {i} is not valid base64") from exc
        if not raw:
            raise ValueError(f"capture {i} is empty")
        with open(os.path.join(batch_dir, f"img_{i:02d}.jpg"), "wb") as f:
            f.write(raw)


# sync on purpose: receive_data hands these to the threadpool
def _write_text(path: str, text: str) -> None:
    with open(path, "w") as f:
        f.write(text)


# same, for the json artefacts a batch keeps
def _write_json(path: str, content: object) -> None:
    with open(path, "w") as f:
        json.dump(content, f, indent=2)


# what a batch ended up holding on disk, so the caller can see what was stored
def _list_batch_files(batch_dir: str) -> list[str]:
    return sorted(os.listdir(batch_dir))


# drop the directory a failed scan made, unless something landed in it
def _discard_empty_batch(batch_dir: str) -> None:
    try:
        if os.path.isdir(batch_dir) and not os.listdir(batch_dir):
            os.rmdir(batch_dir)
    except OSError:
        pass

# liveness probe for nginx and the headset
@app.get("/")
async def root() -> dict:
    return {"status": "alive"}

# run one vr scan through the whole pipeline and store what comes out
@app.post("/receive-data")
async def receive_data(payload: Payload) -> dict:
    # db work goes through the threadpool like everything else here
    def _resolve_company() -> str | None:
        with SessionLocal() as db:
            company = persistence.find_company(db, payload.company_name)
            return company.name if company else None

    # resolved before any paid call, and gives us the stored spelling to file under
    company_name = await run_in_threadpool(_resolve_company)
    if company_name is None:
        raise HTTPException(status_code=404, detail=f"no company named {payload.company_name!r}")

    stamp, batch_dir = await run_in_threadpool(_make_batch_dir, RECEIVE_DIR)

    try:
        try:
            # raw inputs first, so a failed pipeline still leaves the scan on disk
            await run_in_threadpool(_write_captures, batch_dir, payload.captures)
            await run_in_threadpool(
                _write_text, os.path.join(batch_dir, "room.json"),
                payload.room.model_dump_json(indent=2),
            )

            description = await describe_room(payload.room, payload.captures)
            await run_in_threadpool(
                _write_json, os.path.join(batch_dir, "description.json"), description
            )

            print(f"[{stamp}] {len(payload.room.anchors)} anchors, {len(payload.captures)} images saved to {batch_dir}")

            # stages two and three: what is wrong here, then what to do about it
            problems = await determine_problems(json.dumps(description), company_name)
            plan = await conclusion(payload.room.model_dump(), problems)
        # clean up before the handlers below turn this into a status code
        except Exception:
            await run_in_threadpool(_discard_empty_batch, batch_dir)
            raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CompanyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except gemini.GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except gemini.GeminiError as exc:
        print(f"[{stamp}] model request failed: {exc}")
        raise HTTPException(status_code=502, detail="upstream model request failed")

    await run_in_threadpool(_write_text, os.path.join(batch_dir, "problems.txt"), problems)
    try:
        # the model already answered; losing this write must not lose that answer
        def _save() -> list[schemas.ConclusionOut]:
            with SessionLocal() as db:
                persistence.save_plan(plan, company_name, stamp, db)
                # read back inside the session, so the caller gets the ids and
                # timestamps the database filled in rather than the raw plan
                rows = db.scalars(
                    select(models.Conclusion)
                    .where(models.Conclusion.batch == stamp)
                    .order_by(models.Conclusion.created_at, models.Conclusion.id)
                ).all()
                return [schemas.ConclusionOut.model_validate(row) for row in rows]

        conclusions = await run_in_threadpool(_save)
        persisted = True
    except Exception:
        conclusions = []
        persisted = False
        traceback.print_exc()
        print(f"[{stamp}] failed to persist conclusions to the database")

    # written last: save_plan stamps the solution ids into plan first
    await run_in_threadpool(_write_json, os.path.join(batch_dir, "plan.json"), plan)

    files = await run_in_threadpool(_list_batch_files, batch_dir)

    return {
        "status": "ok",
        "company_name": company_name,
        "persisted": persisted, 
        "conclusions": conclusions
    }


# one stored batch, as the web app lists it
class GeminiOutputOut(BaseModel):
    """One Gemini answer that /receive-data already stored on disk."""

    batch: str
    created_at: datetime
    images: int
    anchors: int
    description: str


# load one batch off disk, or None if the pipeline never got that far
def _read_batch(batch: str) -> Optional[GeminiOutputOut]:
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
        # suffixed batch names do not parse, so fall back to the directory mtime
        created_at = datetime.strptime(batch, BATCH_STAMP_FORMAT)
    except ValueError:
        created_at = datetime.fromtimestamp(os.path.getmtime(batch_dir))

    return GeminiOutputOut(
        batch=batch,
        created_at=created_at,
        images=len([n for n in os.listdir(batch_dir) if n.endswith(".jpg")]),
        anchors=anchors,
        description=description,
    )


# every stored batch, newest first
@app.get("/gemini-outputs", response_model=List[GeminiOutputOut])
def list_gemini_outputs() -> list[GeminiOutputOut]:
    """Every Gemini answer stored under RECEIVE_DIR, newest batch first."""
    outputs = []
    for name in sorted(os.listdir(RECEIVE_DIR), reverse=True):
        if not os.path.isdir(os.path.join(RECEIVE_DIR, name)):
            continue
        output = _read_batch(name)
        if output is not None:
            outputs.append(output)
    return outputs


# one stored batch by name
@app.get("/gemini-outputs/{batch}", response_model=GeminiOutputOut)
def get_gemini_output(batch: str) -> GeminiOutputOut:
    # the name goes straight into a path, so allow a bare directory name only
    if batch != os.path.basename(batch) or batch in ("", ".", ".."):
        raise HTTPException(status_code=400, detail=f"invalid batch {batch!r}")

    output = _read_batch(batch)
    if output is None:
        raise HTTPException(status_code=404, detail=f"no gemini output for batch {batch!r}")
    return output


# every company, alphabetical
@app.get("/companies", response_model=List[schemas.CompanyOut])
def list_companies(db: Session = Depends(get_db)) -> Sequence[models.Company]:
    return db.scalars(select(models.Company).order_by(models.Company.name)).all()


# one company, matched whatever the caller's casing
@app.get("/companies/{name}", response_model=schemas.CompanyOut)
def get_company(name: str, db: Session = Depends(get_db)) -> models.Company:
    company = persistence.find_company(db, name)
    if company is None:
        raise HTTPException(status_code=404, detail=f"no company named {name!r}")
    return company


# create a company, or update the one already stored under that name
@app.post("/companies", response_model=schemas.CompanyOut)
def upsert_company(payload: schemas.CompanyIn, db: Session = Depends(get_db)) -> models.Company:
    """Create the company, or update its details if it already exists."""
    company = persistence.find_company(db, payload.name)
    if company is None:
        company = models.Company(
            name=payload.name,
            website=payload.website,
            details=payload.details,
        )
        db.add(company)
        try:
            db.commit()
        # a competing request won the insert, so update its row instead
        except IntegrityError:
            db.rollback()
            company = persistence.find_company(db, payload.name)
            if payload.website is not None:
                company.website = payload.website
            if payload.details is not None:
                company.details = payload.details
    else:
        if payload.website is not None:
            company.website = payload.website
        if payload.details is not None:
            company.details = payload.details
    db.commit()
    db.refresh(company)
    return company


# remove a company and everything ever scanned for it
@app.delete("/companies/{name}")
def delete_company(name: str, db: Session = Depends(get_db)) -> dict:
    company = persistence.find_company(db, name)
    if company is None:
        raise HTTPException(status_code=404, detail=f"no company named {name!r}")
    # conclusions are filed by name with no fk, so they need deleting by hand
    removed = db.execute(
        delete(models.Conclusion).where(
            func.lower(models.Conclusion.company_name) == company.name.lower()
        )
    ).rowcount
    db.delete(company)
    db.commit()
    return {"status": "deleted", "name": company.name, "conclusions_deleted": removed}


# true if any stored conclusion carries this solution id
def _solution_exists(db: Session, solution_id: str) -> bool:
    for stored in db.scalars(select(models.Conclusion)):
        for solution in stored.solutions or []:
            if solution.get("id") == solution_id:
                return True
    return False


# the headset marks a solution as chosen; repeat accepts are deliberate no-ops
@app.post("/accept-solution")
def accept_solution(payload: schemas.AcceptedSolutionIn, db: Session = Depends(get_db)) -> dict:
    """Record a solution the user accepted in VR.

    Accepting the same uuid again is a no-op, so a headset on a flaky link can
    retry without the second attempt looking like a failure.
    """
    if db.get(models.AcceptedSolution, payload.solution_uuid) is None:
        if not _solution_exists(db, payload.solution_uuid):
            raise HTTPException(
                status_code=404, detail=f"no solution with id {payload.solution_uuid!r}"
            )
        db.add(models.AcceptedSolution(solution_uuid=payload.solution_uuid))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

    return {"status": "ok", "solution_uuid": payload.solution_uuid}


# the headset un-chooses a solution
@app.delete("/delete-solution/{solution_uuid}")
def delete_solution(solution_uuid: str, db: Session = Depends(get_db)) -> dict:
    """Drop a solution from the accepted list."""
    accepted = db.get(models.AcceptedSolution, solution_uuid)
    if accepted is None:
        raise HTTPException(status_code=404, detail=f"solution {solution_uuid!r} was not accepted")
    db.delete(accepted)
    db.commit()
    return {"status": "deleted", "solution_uuid": solution_uuid}


# everything this company has accepted, with the conclusion each came from
@app.post("/get-accepted-solutions", response_model=List[schemas.AcceptedSolutionOut])
def get_accepted_solutions(
    payload: schemas.CompanyNameIn, db: Session = Depends(get_db)
) -> list[schemas.AcceptedSolutionOut]:
    """Every solution this company has accepted, with the conclusion around it.

    Solutions live inside each conclusion's JSON column rather than in a table
    of their own, so the mapping is: collect the company's solution ids, ask the
    database which of them were accepted, then keep those.
    """
    conclusions = db.scalars(
        select(models.Conclusion)
        .where(func.lower(models.Conclusion.company_name) == payload.company_name.lower())
        .order_by(models.Conclusion.created_at, models.Conclusion.id)
    ).all()

    # solutions live in a json column, so gather their ids in python first
    solution_ids = [
        solution["id"]
        for conclusion in conclusions
        for solution in conclusion.solutions or []
        if solution.get("id") is not None
    ]
    if not solution_ids:
        return []

    # then let the database say which of those were actually accepted
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
