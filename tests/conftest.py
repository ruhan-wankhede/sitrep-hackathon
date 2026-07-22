import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import SessionLocal, init_db

@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()

@pytest.fixture()
def client_with_db(session):
    # bind the app's session factory to the test's in-memory engine
    SessionLocal.configure(bind=session.get_bind())
    from app.main import app
    return TestClient(app)
