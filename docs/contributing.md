# Contributing to ezrules

Thank you for your interest in contributing to ezrules! This guide will help you get started.

---

## Getting Started

### 1. Fork and Clone

```bash
# Fork on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/ezrules.git
cd ezrules

# Add upstream remote
git remote add upstream https://github.com/sofeikov/ezrules.git
```

### 2. Set Up Development Environment

```bash
# Install dependencies
uv sync

# Set up database
export EZRULES_DB_ENDPOINT="postgresql://postgres:root@localhost:5432/tests"
export EZRULES_TESTING="true"
uv run ezrules init-db --auto-delete
uv run ezrules init-permissions
```

### 3. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

---

## Development Workflow

### Running Tests

```bash
# Run all tests with coverage
PYTHONPATH="$PWD" EZRULES_DB_ENDPOINT="postgresql://postgres:root@localhost:5432/tests" \
EZRULES_TESTING="true" uv run pytest --cov=ezrules.backend --cov=ezrules.core \
--cov-report=term-missing --cov-report=xml tests

# Run specific test file
uv run pytest tests/test_ezruleapp.py -v

# Run specific test
uv run pytest tests/test_ezruleapp.py::test_can_load_root_page -v
```

### Code Quality

```bash
# Run all quality checks
uv run poe check

# This runs:
# - ruff format --check (formatting)
# - mypy (type checking)
# - ruff check (linting)
```

### Fix Code Issues

```bash
# Auto-fix formatting
uv run ruff format

# Auto-fix linting issues
uv run ruff check --fix
```

---

## Contribution Guidelines

### Code Style

- **Formatting**: Use ruff for formatting
- **Type Hints**: Add type hints to all functions
- **Docstrings**: Document public functions and classes
- **Imports**: Place all imports at the top of files, no inline imports

### Testing

- **Coverage**: Maintain >80% test coverage
- **Real Database**: Tests use real PostgreSQL, not mocks
- **Fixtures**: Use existing test fixtures where possible
- **All Tests Must Pass**: No `F` in pytest output before submitting PR

### Commit Messages

Use clear, descriptive commit messages:

```bash
# Good
git commit -m "Add velocity rule support with time-based filtering"
git commit -m "Fix race condition in outcome recording"

# Not ideal
git commit -m "Fix bug"
git commit -m "Update code"
```

---

## Pull Request Process

### Before Submitting

1. **Run all tests**: Ensure they pass
2. **Run code quality checks**: `uv run poe check` must pass
3. **Update documentation**: Add/update docs for new features
4. **Update README**: Document user-facing changes
5. **Update whatsnew.rst**: Add entry for your changes

### Submitting

1. Push your branch to your fork
2. Open a pull request against `main`
3. Provide clear description:
   - What problem does this solve?
   - How does it solve it?
   - Any breaking changes?
   - Screenshots (for UI changes)

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] All tests pass
- [ ] Added new tests
- [ ] Manual testing completed

## Checklist
- [ ] Code quality checks pass
- [ ] Documentation updated
- [ ] README updated (if needed)
- [ ] whatsnew.rst updated
```

---

## Areas for Contribution

### High Priority

- **Performance optimizations** - Profile and optimize slow queries
- **Additional rule patterns** - Pre-built rule templates
- **UI improvements** - Better dashboards and visualizations
- **Documentation** - More examples and use cases

### Good First Issues

Look for issues labeled `good first issue` on GitHub:
- Bug fixes
- Documentation improvements
- Test coverage improvements
- Code cleanup

### Feature Requests

Before working on major features:
1. Open an issue to discuss
2. Get feedback from maintainers
3. Agree on approach
4. Start implementation

---

## Development Tips

### Database Changes

If you modify database models:

```bash
# Drop and recreate test database
uv run ezrules init-db --auto-delete
```

### Testing New Features

Use the data generator for testing:

```bash
uv run ezrules generate-random-data --n-rules 5 --n-events 100
```

### Debugging

Enable debug logging:

```bash
export EZRULES_LOG_LEVEL="DEBUG"
uv run ezrules manager --debug
```

---

## Code Review Process

### What Reviewers Look For

- **Correctness**: Does it work as intended?
- **Tests**: Are there adequate tests?
- **Code Quality**: Is it readable and maintainable?
- **Documentation**: Is it documented?
- **Performance**: Any performance implications?
- **Security**: Any security concerns?

### Addressing Feedback

- Respond to all comments
- Make requested changes
- Push updates to same branch
- Mark conversations as resolved

---

## Community

### Communication

- **GitHub Issues**: Bug reports, feature requests
- **Discussions**: General questions, ideas
- **Pull Requests**: Code contributions

### Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn
- Give credit where due

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

## Questions?

- Open a GitHub issue
- Check existing issues and PRs
- Read the documentation

Thank you for contributing to ezrules! 🎉
