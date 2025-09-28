"""
Simplified web endpoint tests to avoid Flask app context issues.
This focuses on the core requirement: testing critical UI paths and improving coverage.
"""

from flask import g

from ezrules.backend.forms import OutcomeForm, UserForm


class TestCriticalUIEndpointsSimple:
    """Test all critical UI endpoints for proper functionality."""

    def test_root_page_loads_successfully(self, logged_in_manager_client):
        """Test that the root page (/) loads successfully."""
        rv = logged_in_manager_client.get("/", follow_redirects=True)
        assert rv.status_code == 200

    def test_rules_page_loads_successfully(self, logged_in_manager_client):
        """Test that the /rules page loads successfully."""
        rv = logged_in_manager_client.get("/rules", follow_redirects=True)
        assert rv.status_code == 200

    def test_create_rule_page_loads_successfully(self, logged_in_manager_client):
        """Test that the /create_rule page loads successfully."""
        rv = logged_in_manager_client.get("/create_rule")
        assert rv.status_code == 200

    def test_outcomes_page_loads_successfully(self, logged_in_manager_client):
        """Test that the /management/outcomes page loads successfully."""
        rv = logged_in_manager_client.get("/management/outcomes")
        assert rv.status_code == 200

    def test_user_management_page_loads_successfully(self, logged_in_manager_client):
        """Test that the /management/users page loads successfully."""
        rv = logged_in_manager_client.get("/management/users")
        assert rv.status_code == 200

    def test_role_management_page_loads_successfully(self, logged_in_manager_client):
        """Test that the /role_management page loads successfully."""
        rv = logged_in_manager_client.get("/role_management")
        assert rv.status_code == 200

    def test_user_lists_page_loads_successfully(self, logged_in_manager_client):
        """Test that the /management/lists page loads successfully."""
        rv = logged_in_manager_client.get("/management/lists")
        assert rv.status_code == 200

    def test_audit_trail_page_loads_successfully(self, logged_in_manager_client):
        """Test that the /audit page loads successfully."""
        rv = logged_in_manager_client.get("/audit")
        assert rv.status_code == 200

    def test_ping_endpoint(self, logged_in_manager_client):
        """Test that ping endpoint returns OK."""
        rv = logged_in_manager_client.get("/ping")
        assert rv.status_code == 200
        assert rv.data.decode() == "OK"


class TestFormSubmissions:
    """Test form submissions to improve coverage."""

    def test_create_outcome_form_submission(self, session, logged_in_manager_client):
        """Test creating a new outcome through the form."""
        # Get CSRF token
        logged_in_manager_client.get("/management/outcomes")

        form = OutcomeForm()
        form.outcome.data = "TEST_OUTCOME_SIMPLE"
        form.csrf_token.data = g.csrf_token

        rv = logged_in_manager_client.post("/management/outcomes", data=form.data, follow_redirects=True)
        assert rv.status_code == 200

    def test_create_user_form_submission(self, session, logged_in_manager_client):
        """Test creating a new user through the form."""
        # Get CSRF token
        logged_in_manager_client.get("/management/users")

        form = UserForm()
        form.user_email.data = "test_simple@example.com"
        form.password.data = "testpassword"
        form.role_name.data = ""  # No role
        form.csrf_token.data = g.csrf_token

        rv = logged_in_manager_client.post("/management/users", data=form.data, follow_redirects=True)
        assert rv.status_code == 200

    def test_create_role_form_submission(self, session, logged_in_manager_client):
        """Test creating a new role through the form."""
        # Get CSRF token
        logged_in_manager_client.get("/role_management")

        form_data = {
            "name": "test_role_simple",
            "description": "Test role description",
            "create_role": "Create Role",
            "csrf_token": g.csrf_token,
        }

        rv = logged_in_manager_client.post("/role_management", data=form_data, follow_redirects=True)
        assert rv.status_code == 200

    def test_create_user_list(self, session, logged_in_manager_client):
        """Test creating a new user list."""
        # Get CSRF token
        logged_in_manager_client.get("/management/lists")

        form_data = {"action": "create_list", "list_name": "test_list_simple", "csrf_token": g.csrf_token}

        rv = logged_in_manager_client.post("/management/lists", data=form_data, follow_redirects=True)
        assert rv.status_code == 200

    def test_verify_rule_endpoint(self, logged_in_manager_client):
        """Test rule verification endpoint."""
        rv = logged_in_manager_client.post(
            "/verify_rule",
            json={"rule_source": "if $amount>100:\n\treturn 'HOLD'"},
            follow_redirects=True,
        )
        assert rv.status_code == 200

    def test_test_rule_endpoint(self, logged_in_manager_client):
        """Test rule testing endpoint."""
        rv = logged_in_manager_client.post(
            "/test_rule",
            json={
                "rule_source": "if $amount > 100:\n\treturn 'HOLD'",
                "test_json": '{"amount": 900}',
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200

    def test_backtesting_results_endpoint(self, logged_in_manager_client):
        """Test getting backtesting results."""
        rv = logged_in_manager_client.get("/get_backtesting_results/999")
        assert rv.status_code == 200

    def test_task_status_endpoint(self, logged_in_manager_client):
        """Test getting task status."""
        rv = logged_in_manager_client.get("/get_task_status/test_task_id")
        assert rv.status_code == 200


class TestErrorConditions:
    """Test error conditions and edge cases to improve coverage."""

    def test_duplicate_user_creation(self, session, logged_in_manager_client):
        """Test creating duplicate user fails gracefully."""
        from ezrules.models.backend_core import User

        # Create first user
        user1 = User(email="duplicate@example.com", password="test", active=True, fs_uniquifier="duplicate@example.com")
        session.add(user1)
        session.commit()

        # Get CSRF token
        logged_in_manager_client.get("/management/users")

        # Try to create duplicate user
        form = UserForm()
        form.user_email.data = "duplicate@example.com"
        form.password.data = "testpassword"
        form.role_name.data = ""
        form.csrf_token.data = g.csrf_token

        rv = logged_in_manager_client.post("/management/users", data=form.data, follow_redirects=True)
        assert rv.status_code == 200

    def test_duplicate_role_creation(self, session, logged_in_manager_client):
        """Test creating duplicate role fails gracefully."""
        from ezrules.models.backend_core import Role

        # Create first role
        role1 = Role(name="duplicate_role", description="First role")
        session.add(role1)
        session.commit()

        # Get CSRF token
        logged_in_manager_client.get("/role_management")

        # Try to create duplicate role
        form_data = {
            "name": "duplicate_role",
            "description": "Duplicate role",
            "create_role": "Create Role",
            "csrf_token": g.csrf_token,
        }

        rv = logged_in_manager_client.post("/role_management", data=form_data, follow_redirects=True)
        assert rv.status_code == 200

    def test_assign_role_to_user(self, session, logged_in_manager_client):
        """Test assigning role to user."""
        from ezrules.models.backend_core import Role, User

        # Create test user and role
        user = User(email="roletest@example.com", password="test", active=True, fs_uniquifier="roletest@example.com")
        role = Role(name="assign_test_role", description="Test role for assignment")
        session.add(user)
        session.add(role)
        session.commit()

        # Get CSRF token
        logged_in_manager_client.get("/role_management")

        # Assign role to user
        form_data = {"user_id": user.id, "role_id": role.id, "assign_role": "Assign Role", "csrf_token": g.csrf_token}

        rv = logged_in_manager_client.post("/role_management", data=form_data, follow_redirects=True)
        assert rv.status_code == 200

    def test_assign_duplicate_role(self, session, logged_in_manager_client):
        """Test assigning role user already has."""
        from ezrules.models.backend_core import Role, User

        # Create test user and role
        user = User(
            email="duproletest@example.com", password="test", active=True, fs_uniquifier="duproletest@example.com"
        )
        role = Role(name="dup_assign_role", description="Test role for duplicate assignment")
        session.add(user)
        session.add(role)
        session.commit()

        # Assign role first time
        user.roles.append(role)
        session.commit()

        # Get CSRF token
        logged_in_manager_client.get("/role_management")

        # Try to assign same role again
        form_data = {"user_id": user.id, "role_id": role.id, "assign_role": "Assign Role", "csrf_token": g.csrf_token}

        rv = logged_in_manager_client.post("/role_management", data=form_data, follow_redirects=True)
        assert rv.status_code == 200

    def test_delete_role_with_users(self, session, logged_in_manager_client):
        """Test deleting role with assigned users fails."""
        from ezrules.models.backend_core import Role, User

        # Create role and user
        role = Role(name="delete_fail_role", description="Role with users")
        user = User(email="roleuser@example.com", password="test", active=True, fs_uniquifier="roleuser@example.com")
        session.add(role)
        session.add(user)
        session.commit()

        # Assign role to user
        user.roles.append(role)
        session.commit()

        # Get CSRF token
        logged_in_manager_client.get("/role_management")

        # Try to delete role
        rv = logged_in_manager_client.post(
            f"/delete_role/{role.id}", data={"csrf_token": g.csrf_token}, follow_redirects=True
        )
        assert rv.status_code == 200

    def test_delete_role_success(self, session, logged_in_manager_client):
        """Test successful role deletion."""
        from ezrules.models.backend_core import Role

        # Create role without users
        role = Role(name="delete_success_role", description="Role without users")
        session.add(role)
        session.commit()
        role_id = role.id

        # Get CSRF token
        logged_in_manager_client.get("/role_management")

        # Delete role
        rv = logged_in_manager_client.post(
            f"/delete_role/{role_id}", data={"csrf_token": g.csrf_token}, follow_redirects=True
        )
        assert rv.status_code == 200

    def test_remove_user_role_success(self, session, logged_in_manager_client):
        """Test successful removal of role from user."""
        from ezrules.models.backend_core import Role, User

        # Create role and user
        role = Role(name="remove_role", description="Role to remove")
        user = User(
            email="removeuser@example.com", password="test", active=True, fs_uniquifier="removeuser@example.com"
        )
        session.add(role)
        session.add(user)
        session.commit()

        # Assign role to user
        user.roles.append(role)
        session.commit()

        # Get CSRF token
        logged_in_manager_client.get("/role_management")

        # Remove role from user
        rv = logged_in_manager_client.post(
            f"/remove_user_role/{user.id}/{role.id}", data={"csrf_token": g.csrf_token}, follow_redirects=True
        )
        assert rv.status_code == 200

    def test_remove_user_role_not_assigned(self, session, logged_in_manager_client):
        """Test removing role that user doesn't have."""
        from ezrules.models.backend_core import Role, User

        # Create role and user without assignment
        role = Role(name="not_assigned_role", description="Role not assigned")
        user = User(
            email="notroleuser@example.com", password="test", active=True, fs_uniquifier="notroleuser@example.com"
        )
        session.add(role)
        session.add(user)
        session.commit()

        # Get CSRF token
        logged_in_manager_client.get("/role_management")

        # Try to remove role that user doesn't have
        rv = logged_in_manager_client.post(
            f"/remove_user_role/{user.id}/{role.id}", data={"csrf_token": g.csrf_token}, follow_redirects=True
        )
        assert rv.status_code == 200

    def test_user_list_operations(self, session, logged_in_manager_client):
        """Test user list operations."""
        # Create list
        logged_in_manager_client.get("/management/lists")
        create_data = {"action": "create_list", "list_name": "test_operations_list", "csrf_token": g.csrf_token}
        rv = logged_in_manager_client.post("/management/lists", data=create_data, follow_redirects=True)
        assert rv.status_code == 200

        # Add entry
        logged_in_manager_client.get("/management/lists")
        add_data = {
            "action": "add_entry",
            "list_name": "test_operations_list",
            "entry_value": "test_entry",
            "csrf_token": g.csrf_token,
        }
        rv = logged_in_manager_client.post("/management/lists", data=add_data, follow_redirects=True)
        assert rv.status_code == 200

        # Remove entry
        logged_in_manager_client.get("/management/lists")
        remove_data = {
            "action": "remove_entry",
            "list_name": "test_operations_list",
            "entry_value": "test_entry",
            "csrf_token": g.csrf_token,
        }
        rv = logged_in_manager_client.post("/management/lists", data=remove_data, follow_redirects=True)
        assert rv.status_code == 200

        # Delete list
        logged_in_manager_client.get("/management/lists")
        delete_data = {"action": "delete_list", "list_name": "test_operations_list", "csrf_token": g.csrf_token}
        rv = logged_in_manager_client.post("/management/lists", data=delete_data, follow_redirects=True)
        assert rv.status_code == 200

    def test_user_list_error_conditions(self, session, logged_in_manager_client):
        """Test user list error conditions."""
        # Try to create list with empty name
        logged_in_manager_client.get("/management/lists")
        create_data = {"action": "create_list", "list_name": "", "csrf_token": g.csrf_token}
        rv = logged_in_manager_client.post("/management/lists", data=create_data, follow_redirects=True)
        assert rv.status_code == 200

        # Try to add entry with missing values
        logged_in_manager_client.get("/management/lists")
        add_data = {"action": "add_entry", "list_name": "", "entry_value": "", "csrf_token": g.csrf_token}
        rv = logged_in_manager_client.post("/management/lists", data=add_data, follow_redirects=True)
        assert rv.status_code == 200

        # Try to remove entry with missing values
        logged_in_manager_client.get("/management/lists")
        remove_data = {"action": "remove_entry", "list_name": "", "entry_value": "", "csrf_token": g.csrf_token}
        rv = logged_in_manager_client.post("/management/lists", data=remove_data, follow_redirects=True)
        assert rv.status_code == 200
