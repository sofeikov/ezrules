# Architecture Overview

Understanding how ezrules is designed and how its components interact.

---

## System Architecture

ezrules uses a multi-service architecture for scalability and separation of concerns:

```
┌──────────────────────────────────────────────────────────┐
│                     Web Browser                          │
└───────────────────┬──────────────────────────────────────┘
                    │ HTTPS (8888)
                    ▼
┌──────────────────────────────────────────────────────────┐
│                  Manager Service                          │
│  - Web UI for rule management                            │
│  - User authentication                                    │
│  - Analytics dashboards                                   │
│  - Label upload interface                                 │
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
                    │ PostgreSQL
                    │
┌──────────────────────────────────────────────────────────┐
│                 Evaluator Service                         │
│  - REST API for event evaluation                         │
│  - Rule execution engine                                  │
│  - Real-time processing                                   │
│  - Event labeling API                                     │
└───────────────────▲──────────────────────────────────────┘
                    │ HTTP (9999)
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

### 1. Manager Service

**Purpose:** Web interface for human users

**Responsibilities:**
- Rule creation and editing
- Outcome management
- User authentication and authorization
- Analytics dashboards
- Label management and CSV uploads
- User list (blocklist/allowlist) management

**Technology:**
- Flask web framework
- Jinja2 templates
- SQLAlchemy ORM
- Session-based authentication

**Port:** 8888 (default)

---

### 2. Evaluator Service

**Purpose:** API service for rule evaluation

**Responsibilities:**
- Accept events via REST API
- Execute rules against events
- Record outcomes
- Provide labeling API
- Return evaluation results

**Technology:**
- Flask RESTful API
- Python rule execution engine
- SQLAlchemy ORM

**Port:** 9999 (default)

**Design Considerations:**
- Stateless for horizontal scaling
- Optimized for low-latency responses
- Can run multiple instances behind load balancer

---

### 3. Database Layer

**Purpose:** Central data storage

**Database:** PostgreSQL 12+

**Schema Components:**

**Rules Management:**
- `rules` - Rule definitions and code
- `rule_history` - Version history for rules
- `rule_executions` - Execution logs

**Outcomes:**
- `outcomes` - Outcome definitions
- `rule_outcomes` - Mapping between rules and outcomes
- `triggered_outcomes` - Events that triggered outcomes

**Events:**
- `events` - Transaction data
- `event_labels` - Labels assigned to events

**Access Control:**
- `users` - User accounts
- `roles` - Role definitions
- `permissions` - Permission types
- `user_roles` - User-role mappings
- `role_permissions` - Role-permission mappings

**Lists:**
- `user_lists` - List definitions (blocklists, etc.)
- `list_members` - List membership

**Audit:**
- `audit_log` - Complete change history

---

### 4. Rule Engine

**Purpose:** Execute business rules against events

**Architecture:**

```python
# Rule execution flow
def evaluate_event(event_data):
    # 1. Load active rules from database
    rules = get_active_rules()

    # 2. Execute each rule
    for rule in rules:
        try:
            # 3. Execute rule code in sandboxed environment
            result = execute_rule_code(rule.code, event_data)

            # 4. If rule triggers (returns True)
            if result:
                # 5. Record outcome
                for outcome in rule.outcomes:
                    record_outcome(outcome, event_data)

        except Exception as e:
            # 6. Log error, continue with other rules
            log_error(rule, e)

    # 7. Return results
    return get_triggered_outcomes(event_data)
```

**Features:**
- Rules are Python functions
- Full programmatic flexibility
- Error isolation (one rule failure doesn't stop others)
- Execution time tracking
- Rule version control

---

## Data Flow

### Event Evaluation Flow

```
1. External app submits event
   POST /evaluate
   {event_id, amount, user_id, ...}
            │
            ▼
2. Evaluator receives and validates
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

**Manager Service:**
- Session-based authentication
- Password hashing (bcrypt or similar)
- Session cookies with secure flags
- Login/logout endpoints

**Evaluator Service:**
- No built-in authentication (internal service)
- Should be behind API gateway in production
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

**Evaluator Service:**
- Stateless design allows multiple instances
- Deploy behind load balancer
- Shared database handles state
- No inter-process communication needed

**Example Deployment:**
```
Load Balancer (HAProxy/nginx)
    ├─→ Evaluator Instance 1
    ├─→ Evaluator Instance 2
    ├─→ Evaluator Instance 3
    └─→ Evaluator Instance 4
         ↓
    PostgreSQL (single or clustered)
```

**Manager Service:**
- Typically single instance sufficient
- Can scale horizontally with session storage in Redis/PostgreSQL
- Less critical for scaling (admin interface)

### Database Optimization

**Indexing Strategy:**
```sql
-- Event lookups
CREATE INDEX idx_events_event_id ON events(event_id);
CREATE INDEX idx_events_timestamp ON events(created_at);
CREATE INDEX idx_events_user_id ON events(user_id);

-- Outcome queries
CREATE INDEX idx_outcomes_rule_id ON triggered_outcomes(rule_id);
CREATE INDEX idx_outcomes_timestamp ON triggered_outcomes(created_at);

-- Label analytics
CREATE INDEX idx_labels_event_id ON event_labels(event_id);
CREATE INDEX idx_labels_timestamp ON event_labels(created_at);
CREATE INDEX idx_labels_name ON event_labels(label_name);
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

**Evaluator Service:**
- Latency depends heavily on rule complexity (simple rules: ~50ms, complex rules with queries: several seconds)
- Throughput scales with number of instances (stateless design)
- Database connection pooling is critical for performance

**Manager Service:**
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
- Flask (web framework)
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

# Available in rules as:
score = get_user_risk_score(event['user_id'])
```

### Webhooks

Implement webhooks for external notifications:

```python
# On outcome trigger
def notify_webhook(outcome, event):
    requests.post(WEBHOOK_URL, json={
        'outcome': outcome.name,
        'event_id': event.event_id
    })
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
