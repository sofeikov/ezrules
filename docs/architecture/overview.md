# Architecture Overview

Understanding how ezrules is designed and how its components interact.

---

## System Architecture

ezrules uses a unified service architecture where the API service handles both the web interface and rule evaluation:

```
┌──────────────────────────────────────────────────────────┐
│                     Web Browser                          │
└───────────────────┬──────────────────────────────────────┘
                    │ HTTPS (8888)
                    ▼
┌──────────────────────────────────────────────────────────┐
│                   API Service (8888)                      │
│  - FastAPI REST API (/api/v2/*)                           │
│  - Event evaluation (/api/v2/evaluate)                    │
│  - JWT authentication                                     │
│  - Angular frontend served separately (port 4200 dev)    │
└───────────────────┬──────────────────────────────────────┘
                    │
                    │ PostgreSQL
                    ▼
┌──────────────────────────────────────────────────────────┐
│                PostgreSQL Database                        │
│  - Rules and rule history                                 │
│  - Events and outcomes                                    │
│  - Labels and user lists                                  │
│  - Audit trail                                            │
│  - User accounts and permissions                          │
└───────────────────▲──────────────────────────────────────┘
                    │
                    │ HTTP (8888) /api/v2/evaluate
                    │
┌──────────────────────────────────────────────────────────┐
│              External Applications                        │
│  - Payment processors                                     │
│  - Transaction systems                                    │
│  - Integration middleware                                 │
└──────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. API Service

**Purpose:** Unified service for the web interface and rule evaluation API

**Responsibilities:**

- Rule creation and editing
- Outcome management
- User authentication and authorization
- Analytics dashboards
- Label management and CSV uploads
- User list (blocklist/allowlist) management
- Accept events via REST API (`/api/v2/evaluate`)
- Execute rules against events
- Record outcomes
- Return evaluation results

**Technology:**

- FastAPI web framework
- SQLAlchemy ORM
- JWT authentication

**Port:** 8888 (default)

**Design Considerations:**

- Stateless for horizontal scaling
- Optimized for low-latency responses
- Can run multiple instances behind load balancer

---

### 2. Database Layer

**Purpose:** Central data storage

**Database:** PostgreSQL 12+

**Schema Components:**

**Rules & Configuration**

- `rule_engine_config` -- Serialized rule engine payloads
- `rule_engine_config_history` -- Versioned history of the configs
- `rules` -- Rule definitions and logic
- `rule_history` -- Change log produced via SQLAlchemy versioning
- `rule_backtesting_results` -- Records of Celery backtests

**Events & Outcomes**

- `testing_record_log` -- Stored events evaluated by the system
- `testing_results_log` -- Rule outcomes linked to each event
- `allowed_outcomes` -- Whitelist of valid outcome names
- `event_labels` -- Available labels

**User Lists**

- `user_lists` -- List definitions scoped by organisation
- `user_list_entries` -- Individual values contained in each list

**Access Control**

- `user` -- User accounts
- `role` -- Role definitions
- `roles_users` -- Relationship table between users and roles
- `actions` -- Permission action catalog
- `role_actions` -- Permissions assigned to each role (optionally scoped to a resource)

**Audit**

- Explicit `RuleHistory` and `RuleEngineConfigHistory` tables capture rule and config changes with `changed_by` attribution

---

### 3. Rule Engine

**Purpose:** Execute business rules against events

**Architecture:**

```python
from ezrules.core.rule_engine import RuleEngineFactory

def evaluate_event(event_data):
    # 1. Load compiled rule config from rule_engine_config
    rule_engine = RuleEngineFactory.from_json(active_config)

    # 2. Execute each rule (Python code compiled with ast + exec)
    results = rule_engine(event_data)

    # 3. Persist TestingRecordLog + TestingResultsLog entries
    store_results(event_data, results)

    return results
```

**Characteristics:**

- Rules run as native Python functions within the API service process (no sandbox).
- `RuleEngine` aggregates outcomes into `rule_results`, `outcome_counters`, and `outcome_set`.
- New deployments serialise the current rule set into `rule_engine_config` for fast loading.
- Backtesting tasks reuse the same execution pipeline via Celery.

---

## Data Flow

### Event Evaluation Flow

```
1. External app submits event
   POST /api/v2/evaluate
   {event_id, amount, user_id, ...}
            │
            ▼
2. API service receives and validates
            │
            ▼
3. Load active rules from database
            │
            ▼
4. Execute each rule against event
            │
            ▼
5. Record triggered outcomes
            │
            ▼
6. Store event and results in database
            │
            ▼
7. Return response to caller
   {rules_triggered, outcomes, execution_time}
```

### Label Upload Flow

```
1. User uploads CSV via web interface
   POST /upload_labels (file)
            │
            ▼
2. Manager service parses CSV
            │
            ▼
3. Validate event IDs exist
            │
            ▼
4. Validate label names (FRAUD, NORMAL, CHARGEBACK)
            │
            ▼
5. Bulk insert labels to database
            │
            ▼
6. Return upload summary
   {uploaded: N, errors: [...]}
```

---

## Security Architecture

### Authentication

**API Service:**

- Session-based authentication for the web UI
- Password hashing (bcrypt or similar)
- Session cookies with secure flags
- Login/logout endpoints
- The evaluate endpoint (`/api/v2/evaluate`) does not have built-in authentication (internal service)
- Should be behind API gateway in production for the evaluate endpoint
- Network-level access control recommended

### Authorization

**Role-Based Access Control (RBAC):**

```
User → Roles → Permissions → Actions

Example:
  User: analyst@company.com
    ↓
  Roles: [Rule Editor]
    ↓
  Permissions: [create_rule, modify_rule, view_rules, view_outcomes]
    ↓
  Can: Create/edit rules, view outcomes
  Cannot: Delete rules, access audit trail
```

**Permission Enforcement:**

- Checked at endpoint level
- Database queries filtered by user permissions
- Audit trail records all actions

### Audit Trail

All actions are logged:
- Who performed the action
- What was changed
- When it occurred
- Previous and new values (for modifications)

Stored in `audit_log` table with immutable records.

---

## Scalability

### Horizontal Scaling

**API Service:**

- Stateless design allows multiple instances
- Deploy behind load balancer
- Shared database handles state
- No inter-process communication needed

**Example Deployment:**
```
Load Balancer (HAProxy/nginx)
    ├─→ API Instance 1 (port 8888)
    ├─→ API Instance 2 (port 8888)
    ├─→ API Instance 3 (port 8888)
    └─→ API Instance 4 (port 8888)
         ↓
    PostgreSQL (single or clustered)
```

### Database Optimization

**Indexing Strategy:**
```sql
-- Event lookups
CREATE INDEX idx_testing_record_event_id ON testing_record_log(event_id);
CREATE INDEX idx_testing_record_created_at ON testing_record_log(created_at);

-- Outcome queries
CREATE INDEX idx_testing_results_rule_id ON testing_results_log(r_id);

-- Label analytics
CREATE INDEX idx_testing_record_label_id ON testing_record_log(el_id);
```

**Connection Pooling:**

- SQLAlchemy connection pool
- Default: 5 connections per process
- Configurable based on load

**Query Optimization:**

- Eager loading for related data
- Pagination for large result sets
- Caching for frequently accessed data

---

## Performance Characteristics

### Performance Considerations

Performance varies significantly based on:
- Rule complexity and number of active rules
- Database query patterns and indexing
- Hardware resources and network latency
- Event data size and structure

**API Service (Evaluation):**

- Latency depends heavily on rule complexity (simple rules: ~50ms, complex rules with queries: several seconds)
- Throughput scales with number of instances (stateless design)
- Database connection pooling is critical for performance

**API Service (Web UI):**

- Web interface performance depends on database query optimization
- Analytics queries can be resource-intensive for large datasets
- CSV upload performance depends on file size and validation complexity

!!! note "Performance Testing"
    These are general guidelines. Always benchmark with your specific rules and data patterns before production deployment.

### Bottlenecks

**Database:**

- Most common bottleneck
- Mitigate with indexing, connection pooling, read replicas

**Rule Complexity:**

- Complex rules (many queries) slow evaluation
- Monitor execution times
- Optimize or cache expensive operations

**Network:**

- External API calls in rules add latency
- Use async where possible
- Cache external data

---

## Technology Stack

**Backend:**

- Python 3.12+
- FastAPI
- SQLAlchemy (ORM)
- PostgreSQL (database)

**Optional Components:**

- Celery (background tasks)
- Redis (caching, Celery broker)
- Next.js (frontend dashboard)

**Development Tools:**

- uv (package management)
- pytest (testing)
- ruff (linting)
- mypy (type checking)

---

## Extension Points

### Custom Rule Functions

Extend rule capabilities by adding helper functions:

```python
# ezrules/core/rule_helpers.py
def get_user_risk_score(user_id):
    # Custom logic
    return score

# Available in rules as (after registering helper yourself):
score = get_user_risk_score(event['user_id'])
```

### Custom Executors

Implement alternative rule executors:

```python
class CustomRuleExecutor:
    def execute(self, rule_code, event_data):
        # Custom execution logic
        pass
```

---

## Next Steps

- **[Deployment Guide](deployment.md)** - Production deployment patterns
- **[Admin Guide](../user-guide/admin-guide.md)** - System administration
- **[Configuration](../getting-started/configuration.md)** - Configuration options
