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


# the row the headset means, or a 404 naming the id it sent
def _get_conclusion(db: Session, conclusion_id: str) -> models.Conclusion:
    conclusion = db.get(models.Conclusion, conclusion_id)
    if conclusion is None:
        raise HTTPException(status_code=404, detail=f"no conclusion with id {conclusion_id!r}")
    return conclusion


# the headset marks a conclusion as chosen; repeat accepts are deliberate no-ops
@app.post("/accept-solution", response_model=schemas.ConclusionOut)
def accept_solution(
    payload: schemas.AcceptedConclusionIn, db: Session = Depends(get_db)
) -> models.Conclusion:
    """Record a conclusion the user accepted in VR.

    A conclusion is the unit that gets accepted: the problem, its solutions and
    its saving are one panel in the headset and one card in the web app. The
    solutions inside it are that conclusion's detail and are never accepted
    separately, which is why they carry no ids.

    Accepting the same conclusion again is a no-op, so a headset on a flaky link
    can retry without the second attempt looking like a failure.
    """
    conclusion = _get_conclusion(db, payload.conclusion_id)
    conclusion.status = models.STATUS_ACCEPTED
    db.commit()
    db.refresh(conclusion)
    return conclusion


# the headset un-chooses a conclusion
@app.delete("/delete-solution/{conclusion_id}", response_model=schemas.ConclusionOut)
def delete_solution(conclusion_id: str, db: Session = Depends(get_db)) -> models.Conclusion:
    """Drop a conclusion from the accepted list.

    Undoing an accept that never happened is a no-op for the same reason
    accepting twice is: the headset may be retrying, and the end state is what
    it asked for either way.
    """
    conclusion = _get_conclusion(db, conclusion_id)
    conclusion.status = models.STATUS_IN_PROGRESS
    db.commit()
    db.refresh(conclusion)
    return conclusion


# every conclusion this company accepted in VR, oldest first
@app.post("/get-accepted-solutions", response_model=List[schemas.ConclusionOut])
def get_accepted_solutions(
    payload: schemas.CompanyNameIn, db: Session = Depends(get_db)
) -> list[models.Conclusion]:
    """Every conclusion this company has accepted, whole.

    One row per accepted conclusion, with its solutions inline -- the web app
    renders each as one card and does no regrouping.
    """
    return persistence.list_conclusions(db, payload.company_name, accepted_only=True)
