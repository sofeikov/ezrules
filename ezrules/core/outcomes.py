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
