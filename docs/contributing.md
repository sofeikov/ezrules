# Contributing to ezrules

## Fast Path

If you already know the project, use this checklist:

1. Fork and clone
2. `uv sync`
3. Initialize test DB
4. Create branch
5. Implement change + tests
6. Run checks:
   - `uv run poe check`
   - full test suite (coverage command below)
7. Update docs/README/`whatsnew.md` if user-facing behavior changed
8. Open PR with clear description

---

## 1) Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/ezrules.git
cd ezrules
git remote add upstream https://github.com/sofeikov/ezrules.git
```

---

## 2) Set Up Development Environment

```bash
uv sync
uv run ezrules init-db --auto-delete
uv run ezrules init-permissions
```

Create a feature branch:

```bash
git checkout -b feature/your-feature-name
```

---

## 3) Development Workflow

### Run tests (required before PR)

--8<-- "snippets/backend-test-command.md"

### Run quality checks (required before PR)

```bash
uv run poe check
```

### Optional targeted debugging

```bash
uv run pytest tests/test_api_v2_rules.py -v
uv run pytest tests/test_api_v2_rules.py::test_create_rule_success -v
```

---

## 4) Code and Test Expectations

- Keep imports at file top
- Add type hints for new code
- Use existing fixtures where possible
- Prefer real DB interactions in tests over mocking
- Ensure no failing tests before opening PR

---

## 5) Pull Request Checklist

Before submitting:

1. All tests pass
2. `uv run poe check` passes
3. Documentation updated for behavior changes
4. `README.md` updated when user-facing workflows changed
5. `whatsnew.md` updated for notable changes

Suggested PR template:

```markdown
## Description

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Full test suite passed
- [ ] Added/updated tests as needed

## Checklist
- [ ] Quality checks passed
- [ ] Docs updated
```

---

## 6) Review Expectations

Reviewers focus on:

- correctness
- tests and regression risk
- readability and maintainability
- security/performance impact
- docs alignment

---

## 7) Where to Contribute

- performance and query optimizations
- rule-authoring usability
- dashboards and analytics UX
- documentation quality and examples

If proposing a major feature, open an issue first to align scope.

---

## Questions

- Open a GitHub issue
- Check existing issues/PRs
- Read relevant docs pages first
