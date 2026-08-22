"""Database setup: engine, session factory, declarative base."""
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# SQLite by default. To move to Postgres later, only this env var changes:
#   DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1:5433/bernhackt26"
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app.db"
)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

if DATABASE_URL.startswith("sqlite:///"):
    os.makedirs(os.path.dirname(DATABASE_URL.removeprefix("sqlite:///")), exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    # FastAPI serves requests on multiple threads; SQLite objects them by default.
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """Add columns the models gained after the tables were first created.

    create_all() only ever creates whole tables, so a database made by an older
    version of the app keeps its old shape and every query for a new column
    fails with "no such column" -- a 500 on endpoints that used to work.

    Only nullable columns can be filled in this way, which is all the schema has
    needed so far; anything else is reported and left for a real migration.
    """
    inspector = inspect(engine)

    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue  # create_all() just made it, so it is already current

        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            if not column.nullable:
                print(
                    f"[db] {table.name}.{column.name} is missing and NOT NULL; "
                    "add it by hand, it cannot be filled in automatically"
                )
                continue

            type_sql = column.type.compile(engine.dialect)
            with engine.begin() as connection:
                connection.execute(
                    text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {type_sql}")
                )
            print(f"[db] added missing column {table.name}.{column.name} ({type_sql})")


def init_db() -> None:
    """Create any missing tables, and any column an older database lacks."""
    from . import models  # noqa: F401  (registers models on Base before create_all)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
