import abc
from collections.abc import Mapping

from sqlalchemy import func

DEFAULT_OUTCOME_HIERARCHY = ["CANCEL", "HOLD", "RELEASE"]
DEFAULT_OUTCOME_SEVERITY = {outcome: index for index, outcome in enumerate(DEFAULT_OUTCOME_HIERARCHY, start=1)}


class Outcome(abc.ABC):
    """Container for allowed outcomes. All new rules return statements will be checked against it."""

    @abc.abstractmethod
    def get_allowed_outcomes(self):
        """Get the list of allowed outcomes."""

    @abc.abstractmethod
    def add_outcome(self, new_outcome: str):
        """Add a new outcome."""

    @abc.abstractmethod
    def is_allowed_outcome(self, outcome: str):
        """Return if outcome is in the list"""

    @abc.abstractmethod
    def remove_outcome(self, outcome: str):
        """Remove an outcome from the list"""


class FixedOutcome(Outcome):
    def __init__(self):
        self.outcomes = list(DEFAULT_OUTCOME_HIERARCHY)

    def get_allowed_outcomes(self):
        return self.outcomes

    def add_outcome(self, new_outcome: str):
        self.outcomes.append(new_outcome.upper())

    def is_allowed_outcome(self, outcome: str):
        return outcome in self.outcomes

    def remove_outcome(self, outcome: str):
        if outcome in self.outcomes:
            self.outcomes.remove(outcome)


class DatabaseOutcome(Outcome):
    def __init__(self, db_session, o_id: int):
        self.db_session = db_session
        self.o_id = o_id
        self._cached_outcomes = None
        self._initialized = False

    def _ensure_default_outcomes(self):
        """Ensure default outcomes exist in the database"""
        from ezrules.models.backend_core import AllowedOutcome

        existing_outcomes = self.db_session.query(AllowedOutcome).filter_by(o_id=self.o_id).count()
        if existing_outcomes == 0:
            for severity_rank, outcome_name in enumerate(DEFAULT_OUTCOME_HIERARCHY, start=1):
                outcome = AllowedOutcome(
                    outcome_name=outcome_name,
                    severity_rank=severity_rank,
                    o_id=self.o_id,
                )
                self.db_session.add(outcome)
            self.db_session.commit()

    def _ensure_initialized(self):
        """Ensure the database has been initialized with default outcomes"""
        if not self._initialized:
            self._ensure_default_outcomes()
            self._initialized = True

    def _load_outcomes_from_db(self):
        """Load outcomes from database and cache them"""
        from ezrules.models.backend_core import AllowedOutcome

        self._ensure_initialized()
        outcomes = (
            self.db_session.query(AllowedOutcome)
            .filter_by(o_id=self.o_id)
            .order_by(AllowedOutcome.severity_rank.asc(), AllowedOutcome.ao_id.asc())
            .all()
        )
        self._cached_outcomes = [outcome.outcome_name for outcome in outcomes]
        return self._cached_outcomes

    def _resequence_outcomes(self):
        from ezrules.models.backend_core import AllowedOutcome

        outcomes = (
            self.db_session.query(AllowedOutcome)
            .filter_by(o_id=self.o_id)
            .order_by(AllowedOutcome.severity_rank.asc(), AllowedOutcome.ao_id.asc())
            .all()
        )
        for severity_rank, outcome in enumerate(outcomes, start=1):
            outcome.severity_rank = severity_rank
        self.db_session.commit()
        self._cached_outcomes = None

    def get_outcomes_in_severity_order(self):
        return list(self.get_allowed_outcomes())

    def get_outcome_priority_map(self):
        return {outcome: index for index, outcome in enumerate(self.get_outcomes_in_severity_order(), start=1)}

    def get_allowed_outcomes(self):
        if self._cached_outcomes is None:
            self._load_outcomes_from_db()
        return self._cached_outcomes

    def add_outcome(self, new_outcome: str):
        from ezrules.models.backend_core import AllowedOutcome

        self._ensure_initialized()
        new_outcome = new_outcome.upper()

        # Check if outcome already exists
        existing = self.db_session.query(AllowedOutcome).filter_by(outcome_name=new_outcome, o_id=self.o_id).first()

        if not existing:
            max_rank = self.db_session.query(func.max(AllowedOutcome.severity_rank)).filter_by(o_id=self.o_id).scalar()
            outcome = AllowedOutcome(
                outcome_name=new_outcome,
                severity_rank=int(max_rank or 0) + 1,
                o_id=self.o_id,
            )
            self.db_session.add(outcome)
            self.db_session.commit()
            # Invalidate cache to force reload
            self._cached_outcomes = None

    def is_allowed_outcome(self, outcome: str):
        return outcome in self.get_allowed_outcomes()

    def remove_outcome(self, outcome: str):
        from ezrules.models.backend_core import AllowedOutcome

        self._ensure_initialized()
        outcome = outcome.upper()

        # Find and remove the outcome
        existing = self.db_session.query(AllowedOutcome).filter_by(outcome_name=outcome, o_id=self.o_id).first()

        if existing:
            self.db_session.delete(existing)
            self.db_session.commit()
            self._resequence_outcomes()

    def resolve_outcome(self, outcome_counters: Mapping[str, int] | None):
        if not outcome_counters:
            return None

        for outcome in self.get_outcomes_in_severity_order():
            if outcome in outcome_counters:
                return outcome

        return sorted(outcome_counters.keys())[0]
