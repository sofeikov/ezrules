import argparse
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from models.backend_core import Organisation, User
from models.history_meta import versioned_session


def email_type(email):
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(regex, email):
        raise argparse.ArgumentTypeError(f"Invalid email address: {email}")
    return email


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-endpoint", help="The DB endpoint to init the tables in", required=True
    )
    parser.add_argument("--user-email", help="User email", required=True, type=email_type)
    parser.add_argument("--password", help="User password", required=True)

    args = parser.parse_args()

    db_endpoint = args.db_endpoint
    email = args.user_email
    password = args.password

    engine = create_engine(db_endpoint)
    db_session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )
    versioned_session(db_session)

    try:
        db_session.add(
            User(
                email=email,
                password=password,
                active=True,
                fs_uniquifier=email,
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
