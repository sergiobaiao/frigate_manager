from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from .utils.paths import DB_PATH

DATABASE_URL = f"sqlite:///{DB_PATH}" 

database_engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(database_engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    with Session(database_engine) as session:
        yield session
