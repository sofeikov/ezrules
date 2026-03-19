```bash
EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/tests \
EZRULES_TESTING=true \
EZRULES_APP_SECRET=test-secret \
uv run pytest --cov=ezrules.backend --cov=ezrules.core --cov-report=term-missing --cov-report=xml tests
```
