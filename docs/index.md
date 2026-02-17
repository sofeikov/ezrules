# ezrules

**Open-source transaction monitoring and decision automation powered by business rules.**

ezrules provides building blocks to define rule-based decisions, evaluate live events, and close the feedback loop with labels and analytics.

[Start in UI (10-15 min)](getting-started/quickstart.md){ .md-button .md-button--primary }
[Integrate via API](getting-started/integration-quickstart.md){ .md-button }
[Install locally](getting-started/installation.md){ .md-button }

---

## Start Here by Goal

| Goal | Best page | What you get | Typical time |
|---|---|---|---|
| Try the UI end-to-end | [Quick Start](getting-started/quickstart.md) | First rule, first test, first analytics signal | 10-15 min |
| Integrate from another service | [Integration Quickstart](getting-started/integration-quickstart.md) | Auth flow + evaluate + label APIs | 10-20 min |
| Set up local environment | [Installation](getting-started/installation.md) | Running API, DB, and frontend | 20-40 min |
| Configure runtime safely | [Configuration](getting-started/configuration.md) | Env vars and validation checklist | 10-20 min |
| Operate and administer | [Admin Guide](user-guide/admin-guide.md) | Setup, health checks, backup/restore runbooks | 20-40 min |

---

## Start Here by Role

| Role | Start Here | Then |
|---|---|---|
| Analyst | [Quick Start](getting-started/quickstart.md) | [Analyst Guide](user-guide/analyst-guide.md) |
| Administrator | [Installation](getting-started/installation.md) | [Admin Guide](user-guide/admin-guide.md) |
| Integrator | [Integration Quickstart](getting-started/integration-quickstart.md) | [API v2 Reference](api-reference/manager-api.md) |
| Contributor | [Contributing](contributing.md) | [Architecture Overview](architecture/overview.md) |

---

## Key Capabilities

- **Flexible Rule Engine** - Write business rules in a Python-like language with expressive syntax for transaction logic
- **Web Management Interface** - Create and manage rules through an intuitive web UI
- **Role-Based Access Control** - Granular permissions with 27 distinct actions that can be assigned per role
- **Transaction Labeling** - Label events through REST API flows and analyze label trends in the UI
- **Analytics Dashboard** - Monitor transaction volume and outcome trends with configurable time ranges
- **Audit Trail** - Track rule revisions plus user list, outcome, label, and configuration history for compliance requirements

---

## Features at a Glance

| Feature | Description |
|---------|-------------|
| **Rule Engine** | Python-based rule execution with custom logic support |
| **Web Interface** | Web UI for rule creation and management |
| **API Service** | Unified FastAPI service for rule management and real-time evaluation at `/api/v2/evaluate` |
| **Security** | 27 permission actions with role-based access control |
| **Labeling** | API and bulk CSV upload for transaction labels |
| **Analytics** | Time-series charts with 1h, 6h, 12h, 24h, 30d ranges |
| **Database** | PostgreSQL backend with SQLAlchemy ORM |
| **Audit Trail** | History for rules, config, user lists, outcomes, and labels |
| **Backtesting** | Test rule changes against historical data |
| **CLI Tools** | Command-line interface for operations and testing |

---

## Documentation Sections

- **Getting Started**: [Installation](getting-started/installation.md), [Quick Start](getting-started/quickstart.md), [Integration Quickstart](getting-started/integration-quickstart.md), [Configuration](getting-started/configuration.md)
- **User Guide**: [Analyst Guide](user-guide/analyst-guide.md), [Admin Guide](user-guide/admin-guide.md), [Creating Rules](user-guide/creating-rules.md), [Labels and Lists](user-guide/labels-and-lists.md), [Monitoring & Analytics](user-guide/monitoring.md)
- **API Reference**: [API v2 Reference](api-reference/manager-api.md), [Evaluator API](api-reference/evaluator-api.md)
- **Architecture**: [Overview](architecture/overview.md), [Decisions](architecture/decisions.md), [Deployment Guide](architecture/deployment.md)
- **Support**: [Troubleshooting](troubleshooting.md), [Contributing](contributing.md), [What's New](whatsnew.md)

---

## Need Technical Detail?

- System boundaries and tradeoffs: [Architecture Overview](architecture/overview.md)
- Endpoint map and auth contract: [API v2 Reference](api-reference/manager-api.md)
- Evaluate flow details: [Evaluator API](api-reference/evaluator-api.md)

---

## Community & Support

- **GitHub**: [sofeikov/ezrules](https://github.com/sofeikov/ezrules)
- **Issues**: [GitHub Issues](https://github.com/sofeikov/ezrules/issues)
- **License**: [Apache License 2.0](https://github.com/sofeikov/ezrules/blob/main/LICENSE)
