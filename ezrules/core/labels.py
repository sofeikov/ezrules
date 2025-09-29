import abc


class LabelManager(abc.ABC):
    """Container for event labels. All labels will be managed through this interface."""

    @abc.abstractmethod
    def get_all_labels(self):
        """Get the list of all labels."""

    @abc.abstractmethod
    def add_label(self, new_label: str):
        """Add a new label."""

    @abc.abstractmethod
    def label_exists(self, label: str):
        """Return if label exists in the list"""

    @abc.abstractmethod
    def remove_label(self, label: str):
        """Remove a label from the list"""


class DatabaseLabelManager(LabelManager):
    def __init__(self, db_session, o_id: int):
        self.db_session = db_session
        self.o_id = o_id
        self._cached_labels = None
        self._initialized = False

    def _ensure_default_labels(self):
        """Ensure default labels exist in the database"""
        from ezrules.models.backend_core import Label

        existing_labels = self.db_session.query(Label).count()
        if existing_labels == 0:
            default_labels = ["FRAUD", "CHARGEBACK", "NORMAL"]
            for label_name in default_labels:
                label = Label(label=label_name)
                self.db_session.add(label)
            self.db_session.commit()

    def _ensure_initialized(self):
        """Ensure the database has been initialized with default labels"""
        if not self._initialized:
            self._ensure_default_labels()
            self._initialized = True

    def _load_labels_from_db(self):
        """Load labels from database and cache them"""
        from ezrules.models.backend_core import Label

        self._ensure_initialized()
        labels = self.db_session.query(Label).all()
        self._cached_labels = [label.label for label in labels]
        return self._cached_labels

    def get_all_labels(self):
        if self._cached_labels is None:
            self._load_labels_from_db()
        return self._cached_labels

    def add_label(self, new_label: str):
        from ezrules.models.backend_core import Label

        self._ensure_initialized()
        new_label = new_label.strip().upper()

        # Check if label already exists
        existing = self.db_session.query(Label).filter_by(label=new_label).first()

        if not existing:
            label = Label(label=new_label)
            self.db_session.add(label)
            self.db_session.commit()
            # Invalidate cache to force reload
            self._cached_labels = None

    def label_exists(self, label: str):
        return label in self.get_all_labels()

    def remove_label(self, label: str):
        from ezrules.models.backend_core import Label

        self._ensure_initialized()
        label = label.strip().upper()

        # Find and remove the label
        existing = self.db_session.query(Label).filter_by(label=label).first()

        if existing:
            self.db_session.delete(existing)
            self.db_session.commit()
            # Invalidate cache to force reload
            self._cached_labels = None
