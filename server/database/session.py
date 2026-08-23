import os
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app.db"
)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# declarative base every model hangs off
class Base(DeclarativeBase):
    pass


# one session per request, rolled back if the handler blew up
def get_db() -> Iterator["Session"]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# poor man's migration: create_all only makes whole tables, never new columns
def _add_missing_columns() -> None:
    inspector = inspect(engine)

    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue

        # only nullable columns can be backfilled blind; anything else needs a human
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


# bring the database up to the models, called once on startup
def init_db() -> None:
    from . import models  # noqa: F401  (registers models on Base before create_all)

    if DATABASE_URL.startswith("sqlite:///"):
        os.makedirs(os.path.dirname(DATABASE_URL.removeprefix("sqlite:///")), exist_ok=True)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
