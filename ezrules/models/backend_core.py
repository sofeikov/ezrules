import datetime

from flask_security import AsaList, RoleMixin, UserMixin
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from ezrules.models.database import Base
from ezrules.models.history_meta import Versioned


class RolesUsers(Base):
    __tablename__ = "roles_users"
    id = Column(Integer(), primary_key=True)
    user_id = Column("user_id", Integer(), ForeignKey("user.id"))
    role_id = Column("role_id", Integer(), ForeignKey("role.id"))


class Role(Base, RoleMixin):
    __tablename__ = "role"
    id = Column(Integer(), primary_key=True)
    name = Column(String(80), unique=True)
    description = Column(String(255))
    permissions = Column(MutableList.as_mutable(AsaList()), nullable=True)


class User(Base, UserMixin):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True)
    username = Column(String(255), unique=True, nullable=True)
    password = Column(String(255), nullable=False)
    last_login_at = Column(DateTime())
    current_login_at = Column(DateTime())
    last_login_ip = Column(String(100))
    current_login_ip = Column(String(100))
    login_count = Column(Integer)
    active = Column(Boolean())
    fs_uniquifier = Column(String(64), unique=True, nullable=False)
    confirmed_at = Column(DateTime())
    roles = relationship("Role", secondary="roles_users", backref=backref("users", lazy="dynamic"))


class Organisation(Base):
    __tablename__ = "organisation"

    o_id = Column(Integer, unique=True, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    rules: Mapped[list["Rule"]] = relationship()
    re_configs: Mapped[list["RuleEngineConfig"]] = relationship()

    def __repr__(self):
        return f"ID:{self.o_id}, {self.name=}, {len(self.rules)=}"


class RuleEngineConfig(Versioned, Base):
    __tablename__ = "rule_engine_config"

    re_id = Column(Integer, unique=True, primary_key=True)
    label = Column(String, nullable=False)
    config = Column(JSON, nullable=False)

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"))
    org: Mapped["Organisation"] = relationship(back_populates="re_configs")


class Rule(Versioned, Base):
    __tablename__ = "rules"

    r_id: Mapped[int] = mapped_column(unique=True, primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    rid: Mapped[str] = mapped_column()
    logic: Mapped[str] = mapped_column()
    description: Mapped[str] = mapped_column()

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"))
    org: Mapped["Organisation"] = relationship(back_populates="rules")

    backtesting_results: Mapped[list["RuleBackTestingResult"]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"{self.r_id=},{self.created_at=},{self.description=},{self.org=}"


class TestingRecordLog(Base):
    __tablename__ = "testing_record_log"

    tl_id = Column(
        Integer,
        unique=True,
        primary_key=True,
    )
    event = Column(JSON, nullable=False)
    event_timestamp = Column(Integer, nullable=False)
    event_id = Column(String, nullable=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"))

    testing_results: Mapped[list["TestingResultsLog"]] = relationship(
        back_populates="testing_record",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TestingResultsLog(Base):
    __tablename__ = "testing_results_log"

    tr_id = Column(Integer, unique=True, primary_key=True)
    tl_id: Mapped[int] = mapped_column(ForeignKey("testing_record_log.tl_id", ondelete="CASCADE"))
    rule_result = Column(String, nullable=False)

    r_id: Mapped[int] = mapped_column(ForeignKey("rules.r_id"))

    testing_record: Mapped["TestingRecordLog"] = relationship(back_populates="testing_results")


class RuleBackTestingResult(Base):
    __tablename__ = "rule_backtesting_results"

    bt_id = Column(Integer, unique=True, primary_key=True)
    r_id: Mapped[int] = mapped_column(ForeignKey("rules.r_id", ondelete="CASCADE"))
    task_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    rule: Mapped["Rule"] = relationship(back_populates="backtesting_results")


RuleHistory = Rule.__history_mapper__.class_
RuleEngineConfigHistory = RuleEngineConfig.__history_mapper__.class_
