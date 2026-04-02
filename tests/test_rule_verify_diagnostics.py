from tests.test_rules_verify_warnings import _build_rules_client


class TestRuleVerifyDiagnostics:
    def test_verify_rule_returns_structured_syntax_errors(self, session):
        client = _build_rules_client(session)
        token = client.test_data["token"]  # type: ignore[attr-defined]

        response = client.post(
            "/api/v2/rules/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_source": "return ("},
        )

        client.close()

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["params"] == []
        assert data["errors"]
        assert data["errors"][0]["line"] == 1
        assert data["errors"][0]["column"] is not None

    def test_verify_rule_returns_unknown_list_location(self, session):
        client = _build_rules_client(session)
        token = client.test_data["token"]  # type: ignore[attr-defined]

        response = client.post(
            "/api/v2/rules/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_source": 'return "GB" in @DefinitelyMissingList'},
        )

        client.close()

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["referenced_lists"] == ["DefinitelyMissingList"]
        assert data["errors"]
        assert "DefinitelyMissingList" in data["errors"][0]["message"]
        assert data["errors"][0]["line"] == 1
        assert data["errors"][0]["column"] is not None

    def test_verify_rule_returns_referenced_lists_when_valid(self, session):
        client = _build_rules_client(session)
        token = client.test_data["token"]  # type: ignore[attr-defined]

        response = client.post(
            "/api/v2/rules/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_source": 'return "US" in @NACountries and $amount > 0'},
        )

        client.close()

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["referenced_lists"] == ["NACountries"]
        assert data["errors"] == []
        assert data["params"] == ["amount"]
