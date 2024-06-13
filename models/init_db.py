import argparse

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from models.database import Base
from models.history_meta import versioned_session

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-endpoint", help="The DB endpoint to init the tables in")

    args = parser.parse_args()
    db_endpoint = args.db_endpoint

    engine = create_engine(db_endpoint)
    db_session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )
    versioned_session(db_session)
    Base.query = db_session.query_property()
    import models.backend_core

    Base.metadata.create_all(bind=engine)