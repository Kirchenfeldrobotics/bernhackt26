"""Persisting a conclusion() plan into Conclusion rows."""
from sqlalchemy.orm import Session

from . import models


def save_plan(plan: dict, company_name: str, batch: str, db: Session) -> None:
    """Store one batch's conclusions, one row per plan item.

    `plan` is the dict conclusion() returns: {"conclusions": [...]}. Each item
    already groups a problem with its full list of solutions, so this is a
    direct 1:1 mapping from plan item to DB row -- each solution just gains a
    sequential `id` within the row's `solutions` list.
    """
    for c in plan.get("conclusions", []):
        solutions = [
            {**solution, "id": i}
            for i, solution in enumerate(c["solutions"], start=1)
        ]
        db.add(
            models.Conclusion(
                company_name=company_name,
                batch=batch,
                title=c["title"],
                problem=c["problem"],
                solutions=solutions,
                savings_10y_chf=c["savings_10y_chf"],
                anchor=c["anchor"],
            )
        )

    db.commit()
