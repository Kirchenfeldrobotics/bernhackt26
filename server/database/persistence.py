from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models


# the company name is the identity key, so casing and stray spaces must not fork it
def find_company(db: Session, name: str) -> models.Company | None:
    return db.scalar(
        select(models.Company).where(func.lower(models.Company.name) == name.strip().lower())
    )


# store one pipeline plan, one row per conclusion
def save_plan(plan: dict, company_name: str, batch: str, db: Session) -> None:
    for item in plan.get("conclusions", []):
        solutions = item["solutions"]
        # ids are stamped into plan itself: the headset needs them to accept a solution
        for solution in solutions:
            solution["id"] = models.new_id()
        db.add(
            models.Conclusion(
                company_name=company_name,
                batch=batch,
                title=item["title"],
                problem=item["problem"],
                solutions=solutions,
                savings_10y_chf=item["savings_10y_chf"],
                anchor=item["anchor"],
            )
        )

    db.commit()
