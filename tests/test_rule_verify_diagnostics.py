from ezrules.models.backend_core import UserList, UserListEntry
from tests.test_rules_verify_warnings import _build_rules_client


class TestRuleVerifyDiagnostics:
    def test_verify_rule_returns_structured_syntax_errors(self, session):
        client = _build_rules_client(session)
        try:
            token = client.test_data["token"]  # type: ignore[attr-defined]

            response = client.post(
                "/api/v2/rules/verify",
                headers={"Authorization": f"Bearer {token}"},
                json={"rule_source": "return ("},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert data["params"] == []
            assert data["errors"]
            assert data["errors"][0]["line"] == 1
            assert data["errors"][0]["column"] is not None
        finally:
            client.close()

    def test_verify_rule_returns_unknown_list_location(self, session):
        client = _build_rules_client(session)
        try:
            token = client.test_data["token"]  # type: ignore[attr-defined]

            response = client.post(
                "/api/v2/rules/verify",
                headers={"Authorization": f"Bearer {token}"},
                json={"rule_source": 'return "GB" in @DefinitelyMissingList'},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert data["referenced_lists"] == ["DefinitelyMissingList"]
            assert data["errors"]
            assert "DefinitelyMissingList" in data["errors"][0]["message"]
            assert data["errors"][0]["line"] == 1
            assert data["errors"][0]["column"] is not None
        finally:
            client.close()

    def test_verify_rule_returns_referenced_lists_when_valid(self, session):
        client = _build_rules_client(session)
        try:
            token = client.test_data["token"]  # type: ignore[attr-defined]
            org = client.test_data["org"]  # type: ignore[attr-defined]

            user_list = UserList(list_name="VerifyCountries", o_id=int(org.o_id))
            session.add(user_list)
            session.flush()
            session.add(UserListEntry(entry_value="US", ul_id=int(user_list.ul_id)))
            session.commit()

            response = client.post(
                "/api/v2/rules/verify",
                headers={"Authorization": f"Bearer {token}"},
                json={"rule_source": 'return "US" in @VerifyCountries and $amount > 0'},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["referenced_lists"] == ["VerifyCountries"]
            assert data["referenced_outcomes"] == []
            assert data["errors"] == []
            assert data["params"] == ["amount"]
        finally:
            client.close()

    def test_verify_rule_returns_unknown_outcome_location(self, session):
        client = _build_rules_client(session)
        try:
            token = client.test_data["token"]  # type: ignore[attr-defined]

            response = client.post(
                "/api/v2/rules/verify",
                headers={"Authorization": f"Bearer {token}"},
                json={"rule_source": "if $amount > 0:\n\treturn !NEEDS_REVIEW"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert data["referenced_outcomes"] == ["NEEDS_REVIEW"]
            assert data["errors"]
            assert "NEEDS_REVIEW" in data["errors"][0]["message"]
            assert data["errors"][0]["line"] == 2
            assert data["errors"][0]["column"] is not None
        finally:
            client.close()

    def test_verify_rule_rejects_quoted_outcome_returns(self, session):
        client = _build_rules_client(session)
        try:
            token = client.test_data["token"]  # type: ignore[attr-defined]

            response = client.post(
                "/api/v2/rules/verify",
                headers={"Authorization": f"Bearer {token}"},
                json={"rule_source": 'if $amount > 0:\n\treturn "HOLD"'},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert data["referenced_outcomes"] == []
            assert data["errors"]
            assert "Use return !HOLD" in data["errors"][0]["message"]
            assert data["errors"][0]["line"] == 2
            assert data["errors"][0]["column"] is not None
        finally:
            client.close()

    def test_verify_rule_ignores_outcome_tokens_inside_comments(self, session):
        client = _build_rules_client(session)
        try:
            token = client.test_data["token"]  # type: ignore[attr-defined]

            response = client.post(
                "/api/v2/rules/verify",
                headers={"Authorization": f"Bearer {token}"},
                json={"rule_source": "# TODO switch to !REVIEW later\nreturn True"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["referenced_outcomes"] == []
            assert data["errors"] == []
        finally:
            client.close()

    def test_verify_rule_returns_referenced_outcomes_when_valid(self, session):
        client = _build_rules_client(session)
        try:
            token = client.test_data["token"]  # type: ignore[attr-defined]

            response = client.post(
                "/api/v2/rules/verify",
                headers={"Authorization": f"Bearer {token}"},
                json={"rule_source": "if $amount > 0:\n\treturn !HOLD"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["referenced_outcomes"] == ["HOLD"]
            assert data["errors"] == []
            assert data["params"] == ["amount"]
        finally:
            client.close()
