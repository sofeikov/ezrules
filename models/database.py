import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

from models.history_meta import versioned_session

Base = declarative_base()

if "DB_ENDPOINT" in os.environ:
    engine = create_engine(os.environ["DB_ENDPOINT"])
    db_session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )
    versioned_session(db_session)
    Base.query = db_session.query_property()