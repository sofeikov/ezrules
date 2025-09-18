import logging
import os
import subprocess
from random import choice, choices, randint, uniform

import click
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from ezrules.backend.data_utils import Event, eval_and_store
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.rule_updater import (
    RDBRuleEngineConfigProducer,
    RuleManager,
    RuleManagerFactory,
)
from ezrules.models.backend_core import Organisation, TestingRecordLog, User
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.database import Base, db_session
from ezrules.models.history_meta import versioned_session
from ezrules.settings import app_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.group()
def cli():
    pass


@cli.command()
@click.option("--user-email")
@click.option("--password")
def add_user(user_email, password):
    db_endpoint = app_settings.DB_ENDPOINT
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
    except Exception:
        db_session.rollback()
        logger.info("User already exists")
    try:
        db_session.add(Organisation(name="base"))
        db_session.commit()
    except Exception:
        db_session.rollback()


@cli.command()
def init_db():
    db_endpoint = app_settings.DB_ENDPOINT
    logger.info(f"Initalising the DB at {db_endpoint}")
    engine = create_engine(db_endpoint)
    db_session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )
    versioned_session(db_session)
    Base.query = db_session.query_property()

    Base.metadata.create_all(bind=engine)
    logger.info(f"Done initalising the DB at {db_endpoint}")


@cli.command()
@click.option("--port", default="8888")
def manager(port):
    env = os.environ.copy()
    cmd = [
        "gunicorn",
        "-w",
        "1",
        "--threads",
        "4",
        "--bind",
        f"0.0.0.0:{port}",
        "ezrules.backend.ezruleapp:app",
    ]
    subprocess.run(
        cmd,
        env=env,
    )


@cli.command()
@click.option("--port", default="9999")
def evaluator(port):
    env = os.environ.copy()
    cmd = [
        "gunicorn",
        "-w",
        "1",
        "--threads",
        "4",
        "--bind",
        f"0.0.0.0:{port}",
        "ezrules.backend.ezrulevalapp:app",
    ]
    subprocess.run(
        cmd,
        env=env,
    )


@cli.command()
@click.option("--n-rules", default=30)
@click.option("--n-events", default=200)
def generate_random_data(n_rules: int, n_events: int):
    test_attributes = {
        "amount": float,
        "send_country": str,
        "receive_country": str,
        "score": float,
        "is_verified": int,
    }
    fsrm: RuleManager = RuleManagerFactory.get_rule_manager(
        "RDBRuleManager", **{"db": db_session, "o_id": 1}
    )
    rule_engine_config_producer = RDBRuleEngineConfigProducer(db=db_session, o_id=1)
    all_attrs = list(test_attributes)
    for r_ind in range(n_rules):
        n_attrs_by_rule = randint(1, len(all_attrs))
        selected_attrs = set(choices(all_attrs, k=n_attrs_by_rule))

        # Logic is a simple "if" statement randomly combining the attributes above with some thresholds
        conditions = []
        for attr in selected_attrs:
            if isinstance(test_attributes[attr], float):
                threshold = round(uniform(0, 1000), 2)
                conditions.append(f"${attr} > {threshold}")
            elif isinstance(test_attributes[attr], str):
                value = f"'{attr}_value_{randint(1, 10)}'"
                conditions.append(f"${attr} == {value}")
            elif isinstance(test_attributes[attr], int):
                threshold = randint(0, 1)
                conditions.append(f"${attr} == {threshold}")

        logic = " and ".join(conditions)
        outcome = choice(["HOLD", "CANCEL", "RELEASE"])
        logic = f"if {logic}:\n    return '{outcome}'"

        # Create a description for the rule
        description = f"This rule applies when: {', '.join(conditions)}."

        # Create the RuleModel instance
        r = RuleModel(
            rid=f"TestRule_Rule_{r_ind}", logic=logic, description=description, o_id=1
        )

        # Add the rule to the database session and commit it
        db_session.add(r)
        db_session.commit()

        print(f"Generated Rule {r_ind}: {logic}")

        lre = LocalRuleExecutorSQL(db=db_session, o_id=1)
        from datetime import datetime, timedelta

    rule_engine_config_producer.save_config(fsrm)
    # Generate and evaluate events
    for e_ind in range(n_events):
        event_data = {}
        for attr, attr_type in test_attributes.items():
            if isinstance(attr_type, float):
                event_data[attr] = round(uniform(0, 1000), 2)
            elif isinstance(attr_type, str):
                event_data[attr] = f"{attr}_value_{randint(1, 10)}"
            elif isinstance(attr_type, int):
                event_data[attr] = randint(0, 1)

        # Calculate a timestamp within the last month
        current_time = datetime.now()
        start_time = current_time - timedelta(days=30)
        event_timestamp = randint(
            int(start_time.timestamp()), int(current_time.timestamp())
        )

        event = Event(
            event_id=f"TestEvent_Event_{e_ind}",
            event_timestamp=event_timestamp,
            event_data=event_data,
        )

        # Evaluate the event against the rules and store the results
        response = eval_and_store(lre, event)
        print(f"Evaluated Event {e_ind}: {response}")


@cli.command()
def delete_test_data():
    db_session.query(TestingRecordLog).filter(
        TestingRecordLog.event_id.ilike("TestEvent_%")
    ).delete(synchronize_session=False)
    db_session.query(RuleModel).filter(RuleModel.rid.ilike("TestRule_%")).delete(
        synchronize_session=False
    )
    db_session.commit()


if __name__ == "__main__":
    cli()
