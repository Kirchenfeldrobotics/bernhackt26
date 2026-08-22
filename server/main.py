from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List, Optional
import base64
import json
import os
from datetime import datetime

from roomDescription import Anchor, Room, Payload, describe_room
from database import categories, get_db, init_db, models, schemas


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RECEIVE_DIR = os.getenv("RECEIVE_DIR", "/var/www/bernhackt26/received")
os.makedirs(RECEIVE_DIR, exist_ok=True)

@app.get("/")
async def root():
    return {"status": "alive"}

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

    description = describe_room(payload.room, payload.captures, batch_dir)
    with open(f"{batch_dir}/description.json", "w") as f:
        json.dump(description, f, indent=2)

    print(f"[{stamp}] {len(payload.room.anchors)} anchors, {len(payload.captures)} images saved to {batch_dir}")
    return {
        "status": "ok",
        "batch": stamp,
        "received_images": len(payload.captures),
        "description": description,
    }


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
        company = models.Company(name=payload.name, category=payload.category, details=payload.details)
        db.add(company)
    else:
        if payload.category is not None:
            company.category = payload.category
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
