import click
import logging
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from ezrules.models.backend_core import Organisation, User
from ezrules.models.database import Base
from ezrules.models.history_meta import versioned_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.group()
def cli():
    pass


@cli.command()
@click.option("--db-endpoint")
@click.option("--user-email")
@click.option("--password")
def add_user(db_endpoint, user_email, password):
    engine = create_engine(db_endpoint)
    db_session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )
    versioned_session(db_session)

    try:
        db_session.add(
            User(
                email=user_email,
                password=password,
                active=True,
                fs_uniquifier=user_email,
            )
        )
        db_session.commit()
        logger.info(f"Done adding {user_email} to {db_endpoint}")
    except:
        db_session.rollback()
        logger.info("User already exists")
    try:
        db_session.add(Organisation(name="base"))
        db_session.commit()
    except:
        db_session.rollback()


@cli.command()
@click.option("--db-endpoint")
def init_db(db_endpoint):
    logger.info(f"Initalising the DB at {db_endpoint}")
    engine = create_engine(db_endpoint)
    db_session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )
    versioned_session(db_session)
    Base.query = db_session.query_property()
    import ezrules.models.backend_core

    Base.metadata.create_all(bind=engine)
    logger.info(f"Done initalising the DB at {db_endpoint}")


if __name__ == "__main__":
    cli()
