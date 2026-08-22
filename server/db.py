"""Database setup: engine, session factory, declarative base."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# SQLite by default. To move to Postgres later, only this env var changes:
#   DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1:5433/bernhackt26"
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "app.db")
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


def init_db() -> None:
    """Create any missing tables. Call once on app startup."""
    import models  # noqa: F401  (registers models on Base before create_all)

    Base.metadata.create_all(bind=engine)
