"""Scaffold: create the database and show the basic SQLAlchemy usage patterns.

Run it directly to (re)initialise the database and insert a couple of example
rows, then delete the examples and build your real logic on top:

    python scaffold.py
"""
from sqlalchemy import select

import models
from db import SessionLocal, init_db


def main():
    # 1. Create any missing tables. Safe to run repeatedly.
    init_db()

    with SessionLocal() as db:
        # 2. Insert a company (category may be filled in later).
        if not db.scalar(select(models.Company).where(models.Company.name == "Example AG")):
            db.add(models.Company(name="Example AG"))
            db.commit()

        # 3. Assign a category by company name.
        company = db.scalar(select(models.Company).where(models.Company.name == "Example AG"))
        company.category = None  # e.g. "Retail" once categories.CATEGORIES is filled
        db.commit()

        # 4. Query: everything, by category, and everything not yet categorised.
        everything = db.scalars(select(models.Company).order_by(models.Company.name)).all()
        uncategorised = db.scalars(
            select(models.Company).where(models.Company.category.is_(None))
        ).all()

        print(f"{len(everything)} companies, {len(uncategorised)} without a category")
        for c in everything:
            print(f"  {c.name:<30} {c.category or '-'}")


if __name__ == "__main__":
    main()
