import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

from models.history_meta import versioned_session

engine = create_engine(os.environ["DB_ENDPOINT"])
db_session = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)
versioned_session(db_session)
Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
    # import all modules here that might define models so that
    # they will be registered properly on the metadata.  Otherwise,
    # you will have to import them first before calling init_db()
    import models

    Base.metadata.create_all(bind=engine)
    from models.backend_core import Organisation, User

    admin_email = f"sofeykov@gmail.com"
    admin_password = f"12345678"
    try:
        db_session.add(
            User(
                email=admin_email,
                password=admin_password,
                active=True,
                fs_uniquifier=admin_email,
            )
        )
        db_session.commit()
    except:
        db_session.rollback()
        print("User already exists")
    try:
        db_session.add(Organisation(name="base"))
        db_session.commit()
    except:
        db_session.rollback()
        pass
