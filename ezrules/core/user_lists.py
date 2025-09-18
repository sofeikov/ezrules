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
