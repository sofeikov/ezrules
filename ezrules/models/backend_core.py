import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UnicodeText,
    UniqueConstraint,
    types,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from ezrules.models.database import Base


class AsaList(types.TypeDecorator):
    """Store a Python list as a comma-separated UnicodeText column.

    Replaces flask_security.AsaList with an identical implementation.
    """

    impl = UnicodeText

    def process_bind_param(self, value, dialect):
        try:
            return ",".join(value)
        except TypeError:
            return value

    def process_result_value(self, value, dialect):
        if value:
            return value.split(",")
        return []


class RoleMixin:
    """Mixin for Role model definitions.

    Replaces flask_security.RoleMixin with the subset used by this application.
    """

    def __eq__(self, other):
        return self.name == other or self.name == getattr(other, "name", None)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.name)


class UserMixin:
    """Mixin for User model definitions.

    Replaces flask_security.UserMixin with the subset used by this application.
    """

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.active

    def has_role(self, role):
        if isinstance(role, str):
            return role in (r.name for r in self.roles)
        return role in self.roles


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
    password = Column(String(511), nullable=False)
    last_login_at = Column(DateTime())
    current_login_at = Column(DateTime())
    last_login_ip = Column(String(100))
    current_login_ip = Column(String(100))
    login_count = Column(Integer)
    active = Column(Boolean())
    fs_uniquifier = Column(String(64), unique=True, nullable=False)
    confirmed_at = Column(DateTime())
    roles = relationship("Role", secondary="roles_users", backref=backref("users", lazy="dynamic"))


class Action(Base):
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))
    resource_type = Column(String(50))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<Action {self.name}>"


class RoleActions(Base):
    __tablename__ = "role_actions"

    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("role.id"), nullable=False)
    action_id = Column(Integer, ForeignKey("actions.id"), nullable=False)
    resource_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    role = relationship("Role", backref="role_actions")
    action = relationship("Action", backref="role_actions")

    def __repr__(self):
        return f"<RoleAction role_id={self.role_id} action_id={self.action_id}>"


class Organisation(Base):
    __tablename__ = "organisation"

    o_id = Column(Integer, unique=True, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    rules: Mapped[list["Rule"]] = relationship()
    re_configs: Mapped[list["RuleEngineConfig"]] = relationship()

    def __repr__(self):
        return f"ID:{self.o_id}, {self.name=}, {len(self.rules)=}"


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    key = Column(String(100), primary_key=True)
    value_type = Column(String(20), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<RuntimeSetting key={self.key} value_type={self.value_type} value={self.value}>"


class RuleEngineConfig(Base):
    __tablename__ = "rule_engine_config"

    re_id = Column(Integer, unique=True, primary_key=True)
    label = Column(String, nullable=False)
    config = Column(JSON, nullable=False)
    version = Column(Integer, default=1, nullable=False)

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"))
    org: Mapped["Organisation"] = relationship(back_populates="re_configs")


class RuleStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


rule_status_enum_type = SQLEnum(
    RuleStatus,
    name="rule_status_enum",
    values_callable=lambda enum_cls: [status.value for status in enum_cls],
    validate_strings=True,
)


class Rule(Base):
    __tablename__ = "rules"

    r_id: Mapped[int] = mapped_column(unique=True, primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    rid: Mapped[str] = mapped_column()
    logic: Mapped[str] = mapped_column()
    description: Mapped[str] = mapped_column()
    status: Mapped[RuleStatus] = mapped_column(rule_status_enum_type, nullable=False, default=RuleStatus.ACTIVE)
    effective_from: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    approved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    version = Column(Integer, default=1, nullable=False)

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"))
    org: Mapped["Organisation"] = relationship(back_populates="rules")

    backtesting_results: Mapped[list["RuleBackTestingResult"]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"{self.r_id=},{self.created_at=},{self.description=},{self.org=}"


class Label(Base):
    __tablename__ = "event_labels"

    el_id = Column(Integer, unique=True, primary_key=True)
    label = Column(String, unique=True, nullable=False)


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
    outcome_counters = Column(JSON, nullable=True)
    resolved_outcome = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"))
    el_id: Mapped["Label"] = mapped_column(ForeignKey("event_labels.el_id"), nullable=True)

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


class ShadowResultsLog(Base):
    __tablename__ = "shadow_results_log"

    sr_id = Column(Integer, unique=True, primary_key=True)
    tl_id: Mapped[int] = mapped_column(ForeignKey("testing_record_log.tl_id", ondelete="CASCADE"))
    r_id: Mapped[int] = mapped_column(ForeignKey("rules.r_id"))
    rule_result = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))


class AllowedOutcome(Base):
    __tablename__ = "allowed_outcomes"
    __table_args__ = (UniqueConstraint("o_id", "severity_rank", name="uq_allowed_outcomes_org_severity_rank"),)

    ao_id = Column(Integer, unique=True, primary_key=True)
    outcome_name = Column(String, nullable=False)
    severity_rank = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"))
    org: Mapped["Organisation"] = relationship()

    def __repr__(self) -> str:
        return f"{self.ao_id=},{self.outcome_name=},{self.o_id=}"


class UserList(Base):
    __tablename__ = "user_lists"

    ul_id = Column(Integer, unique=True, primary_key=True)
    list_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"))
    org: Mapped["Organisation"] = relationship()

    entries: Mapped[list["UserListEntry"]] = relationship(
        back_populates="user_list",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"{self.ul_id=},{self.list_name=},{self.o_id=}"


class UserListEntry(Base):
    __tablename__ = "user_list_entries"

    ule_id = Column(Integer, unique=True, primary_key=True)
    entry_value = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    ul_id: Mapped[int] = mapped_column(ForeignKey("user_lists.ul_id", ondelete="CASCADE"))
    user_list: Mapped["UserList"] = relationship(back_populates="entries")

    def __repr__(self) -> str:
        return f"{self.ule_id=},{self.entry_value=},{self.ul_id=}"


class RuleBackTestingResult(Base):
    __tablename__ = "rule_backtesting_results"

    bt_id = Column(Integer, unique=True, primary_key=True)
    r_id: Mapped[int] = mapped_column(ForeignKey("rules.r_id", ondelete="CASCADE"))
    task_id = Column(String, nullable=False)
    stored_logic = Column(String, nullable=True)
    proposed_logic = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    rule: Mapped["Rule"] = relationship(back_populates="backtesting_results")


class RuleQualityPair(Base):
    __tablename__ = "rule_quality_pairs"
    __table_args__ = (UniqueConstraint("o_id", "outcome", "label", name="uq_rule_quality_pairs_org_outcome_label"),)

    rqp_id = Column(Integer, unique=True, primary_key=True)
    outcome = Column(String(255), nullable=False)
    label = Column(String(255), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    created_by = Column(String(255), nullable=True)

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), nullable=False)
    org: Mapped["Organisation"] = relationship()


class RuleQualityReport(Base):
    __tablename__ = "rule_quality_reports"

    rqr_id = Column(Integer, unique=True, primary_key=True)
    task_id = Column(String(50), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    min_support = Column(Integer, nullable=False)
    lookback_days = Column(Integer, nullable=False)
    freeze_at = Column(DateTime, nullable=False)
    max_tl_id = Column(Integer, nullable=False, default=0)
    pair_set_hash = Column(String(64), nullable=False, index=True, default="")
    pair_set = Column(JSON, nullable=False, default=list)
    requested_by = Column(String(255), nullable=True)
    error = Column(String, nullable=True)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), nullable=False)
    org: Mapped["Organisation"] = relationship()


class RuleHistory(Base):
    __tablename__ = "rules_history"

    r_id = Column(Integer, primary_key=True)
    version = Column(Integer, primary_key=True)
    rid = Column(String, nullable=False)
    logic = Column(String, nullable=False)
    description = Column(String, nullable=False)
    action = Column(String, nullable=False, default="updated")
    status: Mapped[RuleStatus] = mapped_column(rule_status_enum_type, nullable=False, default=RuleStatus.ACTIVE)
    to_status: Mapped[RuleStatus | None] = mapped_column(rule_status_enum_type, nullable=True)
    effective_from: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class RuleEngineConfigHistory(Base):
    __tablename__ = "rule_engine_config_history"

    re_id = Column(Integer, primary_key=True)
    version = Column(Integer, primary_key=True)
    label = Column(String, nullable=False)
    config = Column(JSON, nullable=False)
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class UserListHistory(Base):
    __tablename__ = "user_list_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ul_id = Column(Integer, nullable=False)
    list_name = Column(String, nullable=False)
    action = Column(String, nullable=False)  # created, renamed, deleted, entry_added, entry_removed, entries_bulk_added
    details = Column(String, nullable=True)  # e.g. old name, entry value, count
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class OutcomeHistory(Base):
    __tablename__ = "outcome_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ao_id = Column(Integer, nullable=False)
    outcome_name = Column(String, nullable=False)
    action = Column(String, nullable=False)  # created, deleted
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class LabelHistory(Base):
    __tablename__ = "label_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    el_id = Column(Integer, nullable=False)
    label = Column(String, nullable=False)
    action = Column(String, nullable=False)  # created, deleted
    details = Column(String, nullable=True)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class UserAccountHistory(Base):
    __tablename__ = "user_account_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    user_email = Column(String, nullable=False)
    action = Column(
        String, nullable=False
    )  # created, updated, deleted, activated, deactivated, role_assigned, role_removed
    details = Column(String, nullable=True)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class RolePermissionHistory(Base):
    __tablename__ = "role_permission_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, nullable=False)
    role_name = Column(String, nullable=False)
    action = Column(String, nullable=False)  # created, updated, deleted, permissions_updated
    details = Column(String, nullable=True)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class FieldTypeHistory(Base):
    __tablename__ = "field_type_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    field_name = Column(String, nullable=False)
    configured_type = Column(String, nullable=False)
    datetime_format = Column(String, nullable=True)
    action = Column(String, nullable=False)  # created, updated, deleted
    details = Column(String, nullable=True)
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class FieldTypeConfig(Base):
    __tablename__ = "field_type_config"

    field_name = Column(String, primary_key=True)
    configured_type = Column(String, nullable=False)
    datetime_format = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), primary_key=True)
    org: Mapped["Organisation"] = relationship()

    def __repr__(self) -> str:
        return f"FieldTypeConfig({self.field_name!r}, {self.configured_type!r}, o_id={self.o_id})"


class FieldObservation(Base):
    __tablename__ = "field_observation"

    field_name = Column(String, primary_key=True)
    observed_json_type = Column(String, primary_key=True)
    last_seen = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    occurrence_count = Column(Integer, default=1, nullable=False)

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), primary_key=True)
    org: Mapped["Organisation"] = relationship()

    def __repr__(self) -> str:
        return f"FieldObservation({self.field_name!r}, {self.observed_json_type!r}, count={self.occurrence_count}, o_id={self.o_id})"


class UserSession(Base):
    __tablename__ = "user_session"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    refresh_token = Column(String(2048), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Invitation(Base):
    __tablename__ = "invitations"

    gid = Column(String(36), primary_key=True)
    email = Column(String(255), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    invited_by = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    accepted_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)

    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), nullable=False)
    org: Mapped["Organisation"] = relationship()


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    gid = Column(String(36), unique=True, nullable=False, index=True)
    key_hash = Column(String(64), nullable=False)
    label = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"))
    org: Mapped["Organisation"] = relationship()


class ApiKeyHistory(Base):
    __tablename__ = "api_key_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key_gid = Column(String(36), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    action = Column(String, nullable=False)  # created, revoked
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)
