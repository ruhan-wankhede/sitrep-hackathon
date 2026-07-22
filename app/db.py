from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

class Base(DeclarativeBase):
    pass

def get_engine():
    return create_engine(settings.database_url, pool_pre_ping=True)

def init_db(engine):
    from app import models  # noqa: F401 — register tables
    Base.metadata.create_all(engine)

SessionLocal = sessionmaker()

def bind_default_engine():
    engine = get_engine()
    init_db(engine)
    SessionLocal.configure(bind=engine)
    return engine
