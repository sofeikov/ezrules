import abc


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


class FixedOutcome(Outcome):
    def __init__(self):
        self.outcomes = ["RELEASE", "HOLD", "CANCEL"]

    def get_allowed_outcomes(self):
        return self.outcomes

    def add_outcome(self, new_outcome: str):
        self.outcomes.append(new_outcome.upper())

    def is_allowed_outcome(self, outcome: str):
        return outcome in self.outcomes


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
            default_outcomes = ["RELEASE", "HOLD", "CANCEL"]
            for outcome_name in default_outcomes:
                outcome = AllowedOutcome(outcome_name=outcome_name, o_id=self.o_id)
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
        outcomes = self.db_session.query(AllowedOutcome).filter_by(o_id=self.o_id).all()
        self._cached_outcomes = [outcome.outcome_name for outcome in outcomes]
        return self._cached_outcomes

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
            outcome = AllowedOutcome(outcome_name=new_outcome, o_id=self.o_id)
            self.db_session.add(outcome)
            self.db_session.commit()
            # Invalidate cache to force reload
            self._cached_outcomes = None

    def is_allowed_outcome(self, outcome: str):
        return outcome in self.get_allowed_outcomes()
