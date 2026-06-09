from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

from ezrules.settings import app_settings

Base = declarative_base()

engine = create_engine(
    app_settings.DB_ENDPOINT,
    pool_size=app_settings.DB_POOL_SIZE,
    max_overflow=app_settings.DB_MAX_OVERFLOW,
    pool_timeout=app_settings.DB_POOL_TIMEOUT_SECONDS,
)
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base.query = db_session.query_property()
