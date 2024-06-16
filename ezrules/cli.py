import argparse
import logging
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from ezrules.models.backend_core import Organisation, User
from ezrules.models.database import Base
from ezrules.models.history_meta import versioned_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def email_type(email):
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(regex, email):
        raise argparse.ArgumentTypeError(f"Invalid email address: {email}")
    return email


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


def main():
    parser = argparse.ArgumentParser(description="ezrules CLI")

    subparsers = parser.add_subparsers(dest="command")

    parser_add_user = subparsers.add_parser("add-user", help="Add a new user")
    parser_add_user.add_argument(
        "--db-endpoint", help="The DB endpoint to init the tables in", required=True
    )
    parser_add_user.add_argument(
        "--user-email", help="User email", required=True, type=email_type
    )
    parser_add_user.add_argument("--password", help="User password", required=True)

    parser_init_db = subparsers.add_parser("init-db", help="Initialize the database")
    parser_init_db.add_argument(
        "--db-endpoint", help="The DB endpoint to init the tables in", required=True
    )

    args = parser.parse_args()
    # parser_init_db.parse_args()

    if args.command == "add-user":
        add_user(args.db_endpoint, args.user_email, args.password)
    elif args.command == "init-db":
        init_db(args.db_endpoint)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
