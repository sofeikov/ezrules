from ezrules.models.backend_core import Label


class TestDeleteLabelAPI:
    """Tests for the DELETE /api/labels/<label_name> endpoint."""

    def test_delete_existing_label(self, session, logged_in_manager_client):
        """Test that an existing label can be deleted via the API."""
        label = Label(label="DELETE_ME")
        session.add(label)
        session.commit()

        response = logged_in_manager_client.delete("/api/labels/DELETE_ME")
        assert response.status_code == 200
        data = response.get_json()
        assert "deleted successfully" in data["message"]

        remaining = session.query(Label).filter_by(label="DELETE_ME").first()
        assert remaining is None

    def test_delete_nonexistent_label_returns_404(self, session, logged_in_manager_client):
        """Test that deleting a label that does not exist returns 404."""
        response = logged_in_manager_client.delete("/api/labels/NONEXISTENT_LABEL_XYZ")
        assert response.status_code == 404
        data = response.get_json()
        assert "not found" in data["error"]

    def test_delete_label_is_case_sensitive(self, session, logged_in_manager_client):
        """Test that the label name must match case exactly as stored."""
        label = Label(label="CASETEST")
        session.add(label)
        session.commit()

        # Wrong case — should 404
        response = logged_in_manager_client.delete("/api/labels/casetest")
        assert response.status_code == 404

        # Correct case — should succeed
        response = logged_in_manager_client.delete("/api/labels/CASETEST")
        assert response.status_code == 200

        remaining = session.query(Label).filter_by(label="CASETEST").first()
        assert remaining is None

    def test_delete_label_strips_whitespace(self, session, logged_in_manager_client):
        """Test that leading/trailing whitespace in the URL path segment is stripped."""
        label = Label(label="TRIMMED")
        session.add(label)
        session.commit()

        # URL-encoded spaces around the label name
        response = logged_in_manager_client.delete("/api/labels/%20TRIMMED%20")
        assert response.status_code == 200

        remaining = session.query(Label).filter_by(label="TRIMMED").first()
        assert remaining is None
