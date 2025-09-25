import abc


class AbstractUserListManager(abc.ABC):
    @abc.abstractmethod
    def add_entry(self, list_name, new_entry):
        """Add new entry to the list"""

    @abc.abstractmethod
    def get_entries(self, list_name):
        """Return all entries for the list"""

    @abc.abstractmethod
    def get_all_entries(self):
        """Get all lists and their entries"""


class StaticUserListManager(AbstractUserListManager):
    def __init__(self):
        self.lists = {
            "MiddleAsiaCountries": ["KZ", "UZ", "KG", "TJ", "TM"],
            "NACountries": ["CA", "US", "MX", "GL"],
            "LatamCountries": [
                "AR",
                "BO",
                "BR",
                "CL",
                "CO",
                "CR",
                "CU",
                "DO",
                "EC",
                "SV",
                "GT",
                "HN",
                "MX",
                "NI",
                "PA",
                "PY",
                "PE",
                "PR",
                "UY",
                "VE",
            ],
        }

    def add_entry(self, list_name, new_entry):
        pass

    def get_entries(self, list_name: str):
        return self.lists[list_name]

    def get_all_entries(self):
        return self.lists


class PersistentUserListManager(AbstractUserListManager):
    def __init__(self, db_session, o_id: int):
        self.db_session = db_session
        self.o_id = o_id
        self._cached_lists = None
        self._initialized = False

    def _get_default_lists(self):
        """Get the default lists that should be created if none exist"""
        return {
            "MiddleAsiaCountries": ["KZ", "UZ", "KG", "TJ", "TM"],
            "NACountries": ["CA", "US", "MX", "GL"],
            "LatamCountries": [
                "AR",
                "BO",
                "BR",
                "CL",
                "CO",
                "CR",
                "CU",
                "DO",
                "EC",
                "SV",
                "GT",
                "HN",
                "MX",
                "NI",
                "PA",
                "PY",
                "PE",
                "PR",
                "UY",
                "VE",
            ],
        }

    def _ensure_default_lists(self):
        """Ensure default lists exist in the database"""
        from ezrules.models.backend_core import UserList, UserListEntry

        existing_lists = self.db_session.query(UserList).filter_by(o_id=self.o_id).count()
        if existing_lists == 0:
            default_lists = self._get_default_lists()
            for list_name, entries in default_lists.items():
                user_list = UserList(list_name=list_name, o_id=self.o_id)
                self.db_session.add(user_list)
                self.db_session.flush()  # Ensure we have the ID

                for entry_value in entries:
                    entry = UserListEntry(entry_value=entry_value, ul_id=user_list.ul_id)
                    self.db_session.add(entry)

            self.db_session.commit()

    def _ensure_initialized(self):
        """Ensure the database has been initialized with default lists"""
        if not self._initialized:
            self._ensure_default_lists()
            self._initialized = True

    def _load_lists_from_db(self):
        """Load lists from database and cache them"""
        from ezrules.models.backend_core import UserList, UserListEntry

        self._ensure_initialized()
        lists = self.db_session.query(UserList).filter_by(o_id=self.o_id).all()

        result = {}
        for user_list in lists:
            entries = self.db_session.query(UserListEntry).filter_by(ul_id=user_list.ul_id).all()
            result[user_list.list_name] = [entry.entry_value for entry in entries]

        self._cached_lists = result
        return self._cached_lists

    def get_entries(self, list_name: str):
        """Return all entries for the list"""
        all_lists = self.get_all_entries()
        if list_name not in all_lists:
            raise KeyError(f"List '{list_name}' not found")
        return all_lists[list_name]

    def get_all_entries(self):
        """Get all lists and their entries"""
        if self._cached_lists is None:
            self._load_lists_from_db()
        return self._cached_lists

    def add_entry(self, list_name, new_entry):
        """Add new entry to the list"""
        from ezrules.models.backend_core import UserList, UserListEntry

        self._ensure_initialized()

        # Find the list
        user_list = self.db_session.query(UserList).filter_by(list_name=list_name, o_id=self.o_id).first()

        if not user_list:
            # Create new list if it doesn't exist
            user_list = UserList(list_name=list_name, o_id=self.o_id)
            self.db_session.add(user_list)
            self.db_session.flush()  # Ensure we have the ID

        # Check if entry already exists
        existing_entry = (
            self.db_session.query(UserListEntry).filter_by(ul_id=user_list.ul_id, entry_value=new_entry).first()
        )

        if not existing_entry:
            entry = UserListEntry(entry_value=new_entry, ul_id=user_list.ul_id)
            self.db_session.add(entry)
            self.db_session.commit()
            # Invalidate cache to force reload
            self._cached_lists = None
