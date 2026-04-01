```bash
EZRULES_DB_ENDPOINT=postgresql://postgres:root@localhost:5432/tests_e2e_local \
EZRULES_TESTING=true \
EZRULES_APP_SECRET=test-secret \
EZRULES_ORG_ID=1 \
uv run pytest --cov=ezrules.backend --cov=ezrules.core --cov-report=term-missing --cov-report=xml tests
```
