"""Persisting a conclusion() plan into Conclusion rows."""
from sqlalchemy.orm import Session

from . import models


def save_plan(plan: dict, company_name: str, batch: str, db: Session) -> None:
    """Store one batch's conclusions, one row per plan item.

    `plan` is the dict conclusion() returns: {"conclusions": [...]}. Each item
    already groups a problem with its full list of solutions, so this is a
    direct 1:1 mapping from plan item to DB row.

    Each solution gains a uuid4 `id` like every other id in the schema,
    assigned into `plan` itself rather than
    into a copy: the caller returns that same dict to the headset, which needs
    the ids to accept a solution later. A counter scoped to one row would not
    do -- accepted_solutions is keyed by the id alone, so it has to be unique
    across every conclusion, not just within one.
    """
    for c in plan.get("conclusions", []):
        solutions = c["solutions"]
        for solution in solutions:
            solution["id"] = models.new_id()
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
