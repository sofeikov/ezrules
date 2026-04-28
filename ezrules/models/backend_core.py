import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UnicodeText,
    UniqueConstraint,
    text,
    types,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from ezrules.core.application_context import get_organization_id
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
        if isinstance(other, str):
            return self.name == other

        other_name = getattr(other, "name", None)
        if other_name is None:
            return False

        self_id = getattr(self, "id", None)
        other_id = getattr(other, "id", None)
        if self_id is not None and other_id is not None:
            return self_id == other_id

        return self.name == other_name and getattr(self, "o_id", None) == getattr(other, "o_id", None)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        role_id = getattr(self, "id", None)
        if role_id is not None:
            return hash(role_id)
        return hash((self.name, getattr(self, "o_id", None)))


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
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_roles_users_user_role"),
        Index("ix_roles_users_role_id_user_id", "role_id", "user_id"),
    )

    id = Column(Integer(), primary_key=True)
    user_id = Column("user_id", Integer(), ForeignKey("user.id"))
    role_id = Column("role_id", Integer(), ForeignKey("role.id"))


def _require_current_organization_id() -> int:
    """Resolve org ownership from explicit context when a caller omits o_id."""
    org_id = get_organization_id()
    if org_id is None:
        raise RuntimeError("An organization context is required when o_id is not provided explicitly.")
    return org_id


class Role(Base, RoleMixin):
    __tablename__ = "role"
    __table_args__ = (
        UniqueConstraint("o_id", "name", name="uq_role_org_name"),
        UniqueConstraint("id", "o_id", name="uq_role_id_org"),
    )

    id = Column(Integer(), primary_key=True)
    name = Column(String(80), nullable=False)
    description = Column(String(255))
    permissions = Column(MutableList.as_mutable(AsaList()), nullable=True)
    o_id = Column(
        Integer(),
        ForeignKey("organisation.o_id"),
        nullable=False,
        index=True,
        default=_require_current_organization_id,
    )
    org: Mapped["Organisation"] = relationship(back_populates="roles")


class User(Base, UserMixin):
    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("id", "o_id", name="uq_user_id_org"),)

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
    o_id = Column(Integer, ForeignKey("organisation.o_id"), nullable=False, index=True)
    org: Mapped["Organisation"] = relationship(back_populates="users")
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
    __table_args__ = (Index("ix_role_actions_role_id_action_id_resource_id", "role_id", "action_id", "resource_id"),)

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

    users: Mapped[list["User"]] = relationship(back_populates="org")
    roles: Mapped[list["Role"]] = relationship(back_populates="org")
    labels: Mapped[list["Label"]] = relationship(back_populates="org")
    rules: Mapped[list["Rule"]] = relationship()
    re_configs: Mapped[list["RuleEngineConfig"]] = relationship()

    def __repr__(self):
        return f"ID:{self.o_id}, {self.name=}, {len(self.rules)=}"


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    key = Column(String(100), primary_key=True)
    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), primary_key=True)
    value_type = Column(String(20), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<RuntimeSetting key={self.key} o_id={self.o_id} value_type={self.value_type} value={self.value}>"


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
    PAUSED = "paused"
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
    execution_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evaluation_lane = Column(String(32), nullable=False, default="main")
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
    __table_args__ = (
        UniqueConstraint("o_id", "label", name="uq_event_labels_org_label"),
        UniqueConstraint("el_id", "o_id", name="uq_event_labels_el_id_o_id"),
    )

    el_id = Column(Integer, unique=True, primary_key=True)
    label = Column(String, nullable=False)
    o_id = Column(
        Integer(),
        ForeignKey("organisation.o_id"),
        nullable=False,
        index=True,
        default=_require_current_organization_id,
    )
    org: Mapped["Organisation"] = relationship(back_populates="labels")


class EventVersion(Base):
    __tablename__ = "event_versions"
    __table_args__ = (
        UniqueConstraint("o_id", "event_id", "event_version", name="uq_event_versions_org_event_version"),
        Index("ix_event_versions_o_id_event_id_version", "o_id", "event_id", "event_version"),
        Index("ix_event_versions_o_id_ingested_at", "o_id", "ingested_at"),
        Index("ix_event_versions_o_id_event_timestamp", "o_id", "event_timestamp"),
    )

    ev_id = Column(Integer, unique=True, primary_key=True)
    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), nullable=False)
    event_id = Column(String, nullable=False)
    event_version = Column(Integer, nullable=False)
    event_timestamp = Column(Integer, nullable=False)
    event_data = Column(JSON, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    source = Column(String(32), nullable=False, default="evaluate")
    supersedes_ev_id: Mapped[int | None] = mapped_column(ForeignKey("event_versions.ev_id"), nullable=True)
    ingested_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC), nullable=False)


class EvaluationDecision(Base):
    __tablename__ = "evaluation_decisions"
    __table_args__ = (
        UniqueConstraint("o_id", "idempotency_key", name="uq_evaluation_decisions_org_idempotency_key"),
        Index("ix_evaluation_decisions_o_id_evaluated_at", "o_id", "evaluated_at"),
        Index("ix_evaluation_decisions_o_id_event_id_version", "o_id", "event_id", "event_version"),
        Index("ix_evaluation_decisions_o_id_served", "o_id", "served"),
    )

    ed_id = Column(Integer, unique=True, primary_key=True)
    ev_id: Mapped[int] = mapped_column(ForeignKey("event_versions.ev_id", ondelete="CASCADE"), nullable=False)
    tl_id: Mapped[int | None] = mapped_column(
        ForeignKey("testing_record_log.tl_id", ondelete="SET NULL"), nullable=True
    )
    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), nullable=False)
    event_id = Column(String, nullable=False)
    event_version = Column(Integer, nullable=False)
    event_timestamp = Column(Integer, nullable=False)
    decision_type = Column(String(32), nullable=False, default="served")
    served = Column(Boolean, nullable=False, default=True)
    idempotency_key = Column(String(128), nullable=True)
    rule_config_label = Column(String(64), nullable=False, default="production")
    rule_config_version = Column(Integer, nullable=True)
    runtime_config = Column(JSON, nullable=True)
    outcome_counters = Column(JSON, nullable=True)
    resolved_outcome = Column(String, nullable=True)
    all_rule_results = Column(JSON, nullable=True)
    evaluated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC), nullable=False)


class EvaluationRuleResult(Base):
    __tablename__ = "evaluation_rule_results"
    __table_args__ = (
        Index("ix_evaluation_rule_results_ed_id_r_id", "ed_id", "r_id"),
        Index("ix_evaluation_rule_results_r_id", "r_id"),
    )

    err_id = Column(Integer, unique=True, primary_key=True)
    ed_id: Mapped[int] = mapped_column(ForeignKey("evaluation_decisions.ed_id", ondelete="CASCADE"), nullable=False)
    r_id: Mapped[int] = mapped_column(ForeignKey("rules.r_id"), nullable=False)
    rule_result = Column(String, nullable=False)


class EventVersionLabel(Base):
    __tablename__ = "event_version_labels"
    __table_args__ = (
        ForeignKeyConstraint(
            ["el_id", "o_id"],
            ["event_labels.el_id", "event_labels.o_id"],
            name="fk_event_version_labels_label_org",
        ),
        UniqueConstraint("o_id", "ev_id", name="uq_event_version_labels_org_event_version"),
        Index("ix_event_version_labels_o_id_assigned_at", "o_id", "assigned_at"),
        Index("ix_event_version_labels_o_id_el_id", "o_id", "el_id"),
    )

    evl_id = Column(Integer, unique=True, primary_key=True)
    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), nullable=False)
    ev_id: Mapped[int] = mapped_column(ForeignKey("event_versions.ev_id", ondelete="CASCADE"), nullable=False)
    el_id: Mapped[int] = mapped_column(Integer(), nullable=False)
    assigned_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC), nullable=False)
    assigned_by = Column(String(255), nullable=True)


class TestingRecordLog(Base):
    __tablename__ = "testing_record_log"
    __table_args__ = (
        ForeignKeyConstraint(
            ["el_id", "o_id"],
            ["event_labels.el_id", "event_labels.o_id"],
            name="fk_testing_record_log_label_org",
        ),
        Index("ix_testing_record_log_o_id_event_id", "o_id", "event_id"),
        Index("ix_testing_record_log_o_id_tl_id", "o_id", "tl_id"),
        Index("ix_testing_record_log_o_id_created_at", "o_id", "created_at"),
    )

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
    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), nullable=False)
    el_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)

    testing_results: Mapped[list["TestingResultsLog"]] = relationship(
        back_populates="testing_record",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TestingResultsLog(Base):
    __tablename__ = "testing_results_log"
    __table_args__ = (Index("ix_testing_results_log_tl_id_r_id", "tl_id", "r_id"),)

    tr_id = Column(Integer, unique=True, primary_key=True)
    tl_id: Mapped[int] = mapped_column(ForeignKey("testing_record_log.tl_id", ondelete="CASCADE"))
    rule_result = Column(String, nullable=False)

    r_id: Mapped[int] = mapped_column(ForeignKey("rules.r_id"))

    testing_record: Mapped["TestingRecordLog"] = relationship(back_populates="testing_results")


class ShadowResultsLog(Base):
    __tablename__ = "shadow_results_log"

    sr_id = Column(Integer, unique=True, primary_key=True)
    tl_id: Mapped[int] = mapped_column(ForeignKey("testing_record_log.tl_id", ondelete="CASCADE"))
    ed_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluation_decisions.ed_id", ondelete="SET NULL"), nullable=True
    )
    r_id: Mapped[int] = mapped_column(ForeignKey("rules.r_id"))
    rule_result = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))


class RuleDeploymentResultsLog(Base):
    __tablename__ = "rule_deployment_results_log"
    __table_args__ = (
        Index("ix_rule_deployment_results_log_o_id_mode_dr_id", "o_id", "mode", "dr_id"),
        Index("ix_rule_deployment_results_log_o_id_r_id", "o_id", "r_id"),
        Index("ix_rule_deployment_results_log_ed_id", "ed_id"),
    )

    dr_id = Column(Integer, unique=True, primary_key=True)
    tl_id: Mapped[int] = mapped_column(ForeignKey("testing_record_log.tl_id", ondelete="CASCADE"))
    ed_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluation_decisions.ed_id", ondelete="SET NULL"), nullable=True
    )
    r_id: Mapped[int] = mapped_column(ForeignKey("rules.r_id"))
    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), nullable=False)
    mode = Column(String(20), nullable=False)
    selected_variant = Column(String(20), nullable=False)
    traffic_percent = Column(Integer, nullable=True)
    bucket = Column(Integer, nullable=True)
    control_result = Column(String, nullable=True)
    candidate_result = Column(String, nullable=True)
    returned_result = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC), nullable=False)


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
    __table_args__ = (
        Index("ix_rule_backtesting_results_task_id", "task_id"),
        Index("ix_rule_backtesting_results_r_id_created_at", "r_id", "created_at"),
    )

    bt_id = Column(Integer, unique=True, primary_key=True)
    r_id: Mapped[int] = mapped_column(ForeignKey("rules.r_id", ondelete="CASCADE"))
    task_id = Column(String, nullable=False)
    stored_logic = Column(String, nullable=True)
    proposed_logic = Column(String, nullable=True)
    result_metrics = Column(JSON, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    rule: Mapped["Rule"] = relationship(back_populates="backtesting_results")


class RuleQualityPair(Base):
    __tablename__ = "rule_quality_pairs"
    __table_args__ = (
        UniqueConstraint("o_id", "outcome", "label", name="uq_rule_quality_pairs_org_outcome_label"),
        Index("ix_rule_quality_pairs_o_id_active", "o_id", "active"),
    )

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
    __table_args__ = (
        Index(
            "ix_rule_quality_reports_cache_lookup",
            "o_id",
            "min_support",
            "lookback_days",
            "pair_set_hash",
            "status",
            "created_at",
        ),
    )

    rqr_id = Column(Integer, unique=True, primary_key=True)
    task_id = Column(String(50), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    min_support = Column(Integer, nullable=False)
    lookback_days = Column(Integer, nullable=False)
    freeze_at = Column(DateTime, nullable=False)
    max_decision_id = Column(Integer, nullable=False, default=0)
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
    __table_args__ = (Index("ix_rules_history_o_id_changed", "o_id", "changed"),)

    r_id = Column(Integer, primary_key=True)
    version = Column(Integer, primary_key=True)
    rid = Column(String, nullable=False)
    logic = Column(String, nullable=False)
    description = Column(String, nullable=False)
    execution_order = Column(Integer, nullable=False, default=1)
    evaluation_lane = Column(String(32), nullable=False, default="main")
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
    __table_args__ = (Index("ix_rule_engine_config_history_o_id_changed", "o_id", "changed"),)

    re_id = Column(Integer, primary_key=True)
    version = Column(Integer, primary_key=True)
    label = Column(String, nullable=False)
    config = Column(JSON, nullable=False)
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class UserListHistory(Base):
    __tablename__ = "user_list_history"
    __table_args__ = (Index("ix_user_list_history_o_id_ul_id_changed", "o_id", "ul_id", "changed"),)

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
    __table_args__ = (Index("ix_outcome_history_o_id_changed", "o_id", "changed"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    ao_id = Column(Integer, nullable=False)
    outcome_name = Column(String, nullable=False)
    action = Column(String, nullable=False)  # created, deleted
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class LabelHistory(Base):
    __tablename__ = "label_history"
    __table_args__ = (Index("ix_label_history_o_id_changed", "o_id", "changed"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    el_id = Column(Integer, nullable=False)
    label = Column(String, nullable=False)
    action = Column(String, nullable=False)  # created, deleted
    details = Column(String, nullable=True)
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class UserAccountHistory(Base):
    __tablename__ = "user_account_history"
    __table_args__ = (Index("ix_user_account_history_o_id_user_id_changed", "o_id", "user_id", "changed"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    user_email = Column(String, nullable=False)
    action = Column(
        String, nullable=False
    )  # created, updated, deleted, activated, deactivated, role_assigned, role_removed
    details = Column(String, nullable=True)
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class RolePermissionHistory(Base):
    __tablename__ = "role_permission_history"
    __table_args__ = (Index("ix_role_permission_history_o_id_role_id_changed", "o_id", "role_id", "changed"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, nullable=False)
    role_name = Column(String, nullable=False)
    action = Column(String, nullable=False)  # created, updated, deleted, permissions_updated
    details = Column(String, nullable=True)
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class FieldTypeHistory(Base):
    __tablename__ = "field_type_history"
    __table_args__ = (Index("ix_field_type_history_o_id_field_name_changed", "o_id", "field_name", "changed"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    field_name = Column(String, nullable=False)
    configured_type = Column(String, nullable=False)
    datetime_format = Column(String, nullable=True)
    required = Column(Boolean, nullable=False, default=False)
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
    required = Column(Boolean, nullable=False, default=False)
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

    o_id: Mapped[int] = mapped_column(ForeignKey("organisation.o_id"), primary_key=True)
    org: Mapped["Organisation"] = relationship()

    def __repr__(self) -> str:
        return f"FieldObservation({self.field_name!r}, {self.observed_json_type!r}, o_id={self.o_id})"


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
    __table_args__ = (Index("ix_api_keys_active_key_hash", "key_hash", postgresql_where=text("revoked_at IS NULL")),)

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
    __table_args__ = (Index("ix_api_key_history_o_id_changed", "o_id", "changed"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key_gid = Column(String(36), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    action = Column(String, nullable=False)  # created, revoked
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class AIRuleAuthoringHistory(Base):
    __tablename__ = "ai_rule_authoring_history"
    __table_args__ = (
        Index("ix_ai_rule_authoring_history_o_id_changed", "o_id", "changed"),
        Index("ix_ai_rule_authoring_history_generation_id", "generation_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    generation_id = Column(String(36), nullable=False)
    r_id = Column(Integer, nullable=True, index=True)
    action = Column(String, nullable=False)  # draft_generated, draft_applied
    mode = Column(String(16), nullable=False)  # create, edit
    evaluation_lane = Column(String(32), nullable=False, default="main")
    provider = Column(String(128), nullable=False)
    model = Column(String(255), nullable=False)
    prompt_excerpt = Column(String(255), nullable=True)
    prompt_hash = Column(String(64), nullable=False)
    validation_status = Column(String(32), nullable=False)  # valid, invalid
    repair_attempted = Column(Boolean, nullable=False, default=False)
    applyable = Column(Boolean, nullable=False, default=False)
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)


class StrictModeHistory(Base):
    __tablename__ = "strict_mode_history"
    __table_args__ = (Index("ix_strict_mode_history_o_id_changed", "o_id", "changed"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    enabled = Column(Boolean, nullable=False)
    action = Column(String, nullable=False)  # enabled, disabled
    details = Column(String, nullable=True)
    o_id = Column(Integer, nullable=False)
    changed = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    changed_by = Column(String, nullable=True)
