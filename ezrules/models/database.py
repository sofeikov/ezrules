import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

from ezrules.models.history_meta import versioned_session
from ezrules.settings import app_settings

Base = declarative_base()

engine = create_engine(app_settings.DB_ENDPOINT)
db_session = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)
versioned_session(db_session)
Base.query = db_session.query_property()
