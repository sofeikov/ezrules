from models.database import Base
from flask_security import UserMixin, RoleMixin, AsaList
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy import (
    Boolean,
    DateTime,
    Column,
    Integer,
    String,
    ForeignKey,
    JSON,
    Text,
)
from core.helpers import LockRecord
import datetime


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
    roles = relationship(
        "Role", secondary="roles_users", backref=backref("users", lazy="dynamic")
    )


class RuleEditLock(Base):
    __tablename__ = "rule_locks"

    rid = Column(String, unique=True, primary_key=True)
    locked_by = Column(String(50), nullable=False)
    expires_on = Column(DateTime())

    def to_lock_record(self) -> LockRecord:
        return LockRecord(
            rid=self.rid,
            locked_by=self.locked_by,
            expires_on=self.expires_on,
        )


class RuleEngineConfig(Base):
    __tablename__ = "rule_engine_config"

    id = Column(Integer, unique=True, primary_key=True)
    label = Column(String, nullable=False)
    config = Column(JSON, nullable=False)


class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, unique=True, primary_key=True)
    revision = Column(Integer)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    rid = Column(String)
    logic = Column(Text)
    description = Column(Text)
