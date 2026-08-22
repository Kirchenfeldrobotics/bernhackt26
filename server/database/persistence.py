"""Persisting a conclusion() plan into Problem/Solution rows."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


def save_plan(plan: dict, company_name: str, batch: str, db: Session) -> None:
    """Store one batch's conclusions, grouping same-text problems into one row.

    `plan` is the dict conclusion() returns: {"conclusions": [...]}. Conclusions
    that share the exact same `problem` text within this batch become one
    Problem with several Solutions, rather than one Problem each.
    """
    conclusions = plan.get("conclusions", [])
    problems_by_text: dict[str, models.Problem] = {}

    for c in conclusions:
        text = c["problem"]
        problem = problems_by_text.get(text)
        if problem is None:
            problem = db.scalar(
                select(models.Problem).where(
                    models.Problem.company_name == company_name,
                    models.Problem.batch == batch,
                    models.Problem.description == text,
                )
            )
        if problem is None:
            problem = models.Problem(company_name=company_name, batch=batch, description=text)
            db.add(problem)
        problems_by_text[text] = problem

        problem.solutions.append(
            models.Solution(
                title=c["title"],
                explanation=c["solution"],
                url=c.get("product_url"),
            )
        )

    db.commit()
