class TestOutcomesAPI:
    """Tests for the /api/outcomes endpoints (GET, POST, DELETE)."""

    def test_get_outcomes_returns_list(self, session, logged_in_manager_client):
        """Test that GET /api/outcomes returns a list of outcomes."""
        response = logged_in_manager_client.get("/api/outcomes")
        assert response.status_code == 200
        data = response.get_json()
        assert "outcomes" in data
        assert isinstance(data["outcomes"], list)

    def test_get_outcomes_includes_defaults(self, session, logged_in_manager_client):
        """Test that the default outcomes (RELEASE, HOLD, CANCEL) are present."""
        response = logged_in_manager_client.get("/api/outcomes")
        assert response.status_code == 200
        data = response.get_json()
        for default in ["RELEASE", "HOLD", "CANCEL"]:
            assert default in data["outcomes"]

    def test_create_outcome_success(self, session, logged_in_manager_client):
        """Test that POST /api/outcomes creates a new outcome."""
        response = logged_in_manager_client.post(
            "/api/outcomes",
            json={"outcome": "NEWOUTCOME"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["outcome"] == "NEWOUTCOME"

        # Verify it appears in the list
        response = logged_in_manager_client.get("/api/outcomes")
        assert "NEWOUTCOME" in response.get_json()["outcomes"]

    def test_create_outcome_uppercased(self, session, logged_in_manager_client):
        """Test that outcome names are stored in uppercase."""
        response = logged_in_manager_client.post(
            "/api/outcomes",
            json={"outcome": "lowercase"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["outcome"] == "LOWERCASE"

    def test_create_outcome_duplicate_returns_409(self, session, logged_in_manager_client):
        """Test that creating a duplicate outcome returns 409."""
        # RELEASE is a default outcome
        response = logged_in_manager_client.post(
            "/api/outcomes",
            json={"outcome": "RELEASE"},
        )
        assert response.status_code == 409
        data = response.get_json()
        assert data["success"] is False
        assert "already exists" in data["error"]

    def test_create_outcome_empty_name_returns_400(self, session, logged_in_manager_client):
        """Test that an empty outcome name returns 400."""
        response = logged_in_manager_client.post(
            "/api/outcomes",
            json={"outcome": "   "},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "required" in data["error"]

    def test_create_outcome_no_data_returns_400(self, session, logged_in_manager_client):
        """Test that POST with no JSON body returns 400."""
        response = logged_in_manager_client.post(
            "/api/outcomes",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_delete_outcome_success(self, session, logged_in_manager_client):
        """Test that DELETE /api/outcomes/<name> removes an outcome."""
        # First create an outcome to delete
        logged_in_manager_client.post(
            "/api/outcomes",
            json={"outcome": "TODELETE"},
        )

        response = logged_in_manager_client.delete("/api/outcomes/TODELETE")
        assert response.status_code == 200
        data = response.get_json()
        assert "deleted successfully" in data["message"]

        # Verify it's gone
        response = logged_in_manager_client.get("/api/outcomes")
        assert "TODELETE" not in response.get_json()["outcomes"]

    def test_delete_outcome_nonexistent_returns_404(self, session, logged_in_manager_client):
        """Test that deleting a non-existent outcome returns 404."""
        response = logged_in_manager_client.delete("/api/outcomes/NONEXISTENT_XYZ")
        assert response.status_code == 404
        data = response.get_json()
        assert "not found" in data["error"]

    def test_delete_outcome_case_insensitive(self, session, logged_in_manager_client):
        """Test that DELETE normalises the outcome name to uppercase."""
        # Create an outcome
        logged_in_manager_client.post(
            "/api/outcomes",
            json={"outcome": "CASETEST"},
        )

        # Delete using lowercase — should still work because endpoint uppercases
        response = logged_in_manager_client.delete("/api/outcomes/casetest")
        assert response.status_code == 200

        # Verify it's gone
        response = logged_in_manager_client.get("/api/outcomes")
        assert "CASETEST" not in response.get_json()["outcomes"]
