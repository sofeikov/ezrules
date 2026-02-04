"""Tests for the POST /api/rules endpoint (Create Rule API)."""


class TestCreateRuleAPI:
    """Test suite for the create rule API endpoint."""

    def test_api_create_rule_success(self, session, logged_in_manager_client):
        """Test that POST /api/rules creates a rule and returns correct response."""
        rv = logged_in_manager_client.post(
            "/api/rules",
            json={
                "rid": "test_create_success",
                "description": "A test rule created via API",
                "logic": "if $amount > 100:\n\treturn 'HOLD'",
            },
        )
        assert rv.status_code == 200

        data = rv.get_json()
        assert data["success"] is True
        assert data["message"] == "Rule created successfully"
        assert "rule" in data

        rule = data["rule"]
        assert rule["rid"] == "test_create_success"
        assert rule["description"] == "A test rule created via API"
        assert rule["logic"] == "if $amount > 100:\n\treturn 'HOLD'"
        assert rule["r_id"] is not None
        assert isinstance(rule["r_id"], int)
        assert rule["revisions"] == []

    def test_api_create_rule_persists_to_db(self, session, logged_in_manager_client):
        """Test that a created rule is actually persisted in the database."""
        from ezrules.models.backend_core import Rule as RuleModel

        rv = logged_in_manager_client.post(
            "/api/rules",
            json={
                "rid": "test_create_persists",
                "description": "Persistence test",
                "logic": "if $amount > 200:\n\treturn 'REVIEW'",
            },
        )
        assert rv.status_code == 200

        data = rv.get_json()
        created_r_id = data["rule"]["r_id"]

        # Query the database directly to confirm the rule exists
        db_rule = session.query(RuleModel).filter_by(r_id=created_r_id).one()
        assert db_rule.rid == "test_create_persists"
        assert db_rule.description == "Persistence test"
        assert db_rule.logic == "if $amount > 200:\n\treturn 'REVIEW'"

    def test_api_create_rule_appears_in_list(self, session, logged_in_manager_client):
        """Test that a created rule appears in GET /api/rules."""
        rv = logged_in_manager_client.post(
            "/api/rules",
            json={
                "rid": "test_create_in_list",
                "description": "List appearance test",
                "logic": "if $amount > 300:\n\treturn 'HOLD'",
            },
        )
        assert rv.status_code == 200

        # Fetch the rules list
        rv = logged_in_manager_client.get("/api/rules")
        assert rv.status_code == 200

        data = rv.get_json()
        rids = [r["rid"] for r in data["rules"]]
        assert "test_create_in_list" in rids

    def test_api_create_rule_missing_rid(self, session, logged_in_manager_client):
        """Test that POST /api/rules returns 400 when rid is missing."""
        rv = logged_in_manager_client.post(
            "/api/rules",
            json={
                "rid": "",
                "description": "Missing rid test",
                "logic": "if $amount > 100:\n\treturn 'HOLD'",
            },
        )
        assert rv.status_code == 400

        data = rv.get_json()
        assert data["success"] is False
        assert "Rule ID" in data["error"]

    def test_api_create_rule_missing_description(self, session, logged_in_manager_client):
        """Test that POST /api/rules returns 400 when description is missing."""
        rv = logged_in_manager_client.post(
            "/api/rules",
            json={
                "rid": "test_no_desc",
                "description": "",
                "logic": "if $amount > 100:\n\treturn 'HOLD'",
            },
        )
        assert rv.status_code == 400

        data = rv.get_json()
        assert data["success"] is False
        assert "Description" in data["error"]

    def test_api_create_rule_missing_logic(self, session, logged_in_manager_client):
        """Test that POST /api/rules returns 400 when logic is missing."""
        rv = logged_in_manager_client.post(
            "/api/rules",
            json={
                "rid": "test_no_logic",
                "description": "No logic test",
                "logic": "",
            },
        )
        assert rv.status_code == 400

        data = rv.get_json()
        assert data["success"] is False
        assert "Logic" in data["error"]

    def test_api_create_rule_no_body(self, session, logged_in_manager_client):
        """Test that POST /api/rules returns 400 when no JSON body is provided."""
        rv = logged_in_manager_client.post(
            "/api/rules",
            data="not json",
            content_type="text/plain",
        )
        assert rv.status_code == 400

        data = rv.get_json()
        assert data["success"] is False
        assert "No data provided" in data["error"]

    def test_api_create_rule_invalid_logic(self, session, logged_in_manager_client):
        """Test that POST /api/rules returns 400 for invalid rule logic."""
        rv = logged_in_manager_client.post(
            "/api/rules",
            json={
                "rid": "test_invalid_logic",
                "description": "Invalid logic test",
                "logic": "this is not valid python syntax !!!",
            },
        )
        assert rv.status_code == 400

        data = rv.get_json()
        assert data["success"] is False
        assert "Invalid rule logic" in data["error"]

    def test_api_create_rule_detail_retrievable(self, session, logged_in_manager_client):
        """Test that a created rule can be retrieved via GET /api/rules/<id>."""
        rv = logged_in_manager_client.post(
            "/api/rules",
            json={
                "rid": "test_create_retrieve",
                "description": "Retrievable rule",
                "logic": "if $amount > 100:\n\treturn 'HOLD'",
            },
        )
        assert rv.status_code == 200
        created_r_id = rv.get_json()["rule"]["r_id"]

        # Retrieve via detail endpoint
        rv = logged_in_manager_client.get(f"/api/rules/{created_r_id}")
        assert rv.status_code == 200

        data = rv.get_json()
        assert data["rid"] == "test_create_retrieve"
        assert data["description"] == "Retrievable rule"
        assert data["logic"] == "if $amount > 100:\n\treturn 'HOLD'"
