"""Scaffold: create the database and show the basic SQLAlchemy usage patterns.

Run it directly to (re)initialise the database and insert a couple of example
rows, then delete the examples and build your real logic on top:

    python -m database.scaffold
"""
from sqlalchemy import select

from . import models
from .session import SessionLocal, init_db


def main():
    # 1. Create any missing tables. Safe to run repeatedly.
    init_db()

    with SessionLocal() as db:
        # 2. Insert a company.
        if not db.scalar(select(models.Company).where(models.Company.name == "Example AG")):
            db.add(models.Company(name="Example AG"))
            db.commit()

        # 3. Update one by name.
        company = db.scalar(select(models.Company).where(models.Company.name == "Example AG"))
        company.details = "An example company, added by the scaffold."
        db.commit()

        # 4. Query: everything, and everything still missing a description.
        everything = db.scalars(select(models.Company).order_by(models.Company.name)).all()
        undescribed = db.scalars(
            select(models.Company).where(models.Company.details.is_(None))
        ).all()

        print(f"{len(everything)} companies, {len(undescribed)} without a description")
        for c in everything:
            print(f"  {c.name:<30} {c.details or '-'}")


if __name__ == "__main__":
    main()
