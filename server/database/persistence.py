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
    """Write the plan's conclusions, exactly as the model produced them.

    A conclusion is the unit the headset accepts, so its row id is the only id
    involved. The solutions inside it are stored as they came -- they are the
    detail of one conclusion, never accepted on their own, and need no ids.
    """
    for item in plan.get("conclusions", []):
        db.add(
            models.Conclusion(
                company_name=company_name,
                batch=batch,
                title=item["title"],
                problem=item["problem"],
                solutions=item["solutions"],
                savings_10y_chf=item["savings_10y_chf"],
                anchor=item["anchor"],
            )
        )

    db.commit()


# every conclusion this company has, newest scan last
def list_conclusions(
    db: Session, company_name: str, *, accepted_only: bool = False
) -> list[models.Conclusion]:
    query = select(models.Conclusion).where(
        func.lower(models.Conclusion.company_name) == company_name.strip().lower()
    )
    if accepted_only:
        query = query.where(models.Conclusion.status == models.STATUS_ACCEPTED)
    return list(
        db.scalars(query.order_by(models.Conclusion.created_at, models.Conclusion.id)).all()
    )
