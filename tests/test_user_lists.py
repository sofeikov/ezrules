from ezrules.core.user_lists import StaticUserListManager


def test_can_add_to_static():
    m = StaticUserListManager()
    m.add_entry("new list", 'new_value')
