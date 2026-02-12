# Welcome to ezrules

**Open-source transaction monitoring engine for business rules**

ezrules provides a Python-based framework for defining, managing, and executing business rules with a web-based management interface and scalable infrastructure for rule execution and backtesting.

---

## What is ezrules?

ezrules is designed for organizations that need to monitor transactions, detect fraud, and enforce business logic at scale. Whether you're building a financial compliance system, automating business decisions, or analyzing transaction patterns, ezrules provides the tools you need.

### Key Capabilities

- **Flexible Rule Engine** - Write business rules in a Python-like language with expressive syntax for transaction logic
- **Web Management Interface** - Create and manage rules through an intuitive web UI
- **Role-Based Access Control** - Granular permissions with 27 distinct actions that can be assigned per role
- **Transaction Labeling** - Label events through REST API flows and analyze label trends in the UI
- **Analytics Dashboard** - Monitor transaction volume and outcome trends with configurable time ranges
- **Audit Trail** - Track rule revisions plus user list, outcome, label, and configuration history for compliance requirements

---

## Quick Links

### Quick Start
Get up and running in minutes with our quick start guide
[-> Quick Start](getting-started/quickstart.md)

### User Guides
Learn how to use ezrules for your role - analyst, admin, or developer
[-> Guides](user-guide/analyst-guide.md)

### API Reference
Integrate ezrules with your applications using our REST APIs
[-> API Docs](api-reference/manager-api.md)

### Architecture
Understand how ezrules works under the hood
[-> Architecture](architecture/overview.md)

---

## Use Cases

### Financial Transaction Monitoring
Real-time fraud detection and compliance checking with configurable rules and API-driven outcomes.

### Enterprise Compliance
Role-based access control with complete audit trails to meet regulatory requirements and internal policies.

### Fraud Analytics
Comprehensive transaction labeling system for performance analysis, false positive reduction, and model validation.

### Business Rule Automation
Automated decision-making based on configurable business logic without requiring code deployments.

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

## Architecture Overview

ezrules uses a unified service architecture where the API service handles both the web interface and rule evaluation:

```
┌─────────────────┐
│   Web Browser   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  API Service    │────>│    PostgreSQL   │
│   (Port 8888)   │     │    Database     │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│      Redis      │────>│ Celery Worker   │
│ (Task Broker)   │     │  (Backtesting)  │
└─────────────────┘     └─────────────────┘
         ▲
         │
┌─────────────────┐
│ External Apps   │
│ POST            │
│ /api/v2/evaluate│
└─────────────────┘
```

- **API Service**: Unified service for web UI, rule management, and real-time rule evaluation
- **Database**: Central storage for rules, events, and analytics
- **Celery Workers**: Background task processing for rule backtesting

---

## Getting Started

Ready to start using ezrules? Follow our installation guide:

[Get Started ->](getting-started/installation.md){ .md-button .md-button--primary }

Or jump straight to a practical example:

[Quick Start ->](getting-started/quickstart.md){ .md-button }

---

## Community & Support

- **GitHub**: [sofeikov/ezrules](https://github.com/sofeikov/ezrules)
- **Issues**: Report bugs or request features on [GitHub Issues](https://github.com/sofeikov/ezrules/issues)
- **License**: MIT License - see [LICENSE](https://github.com/sofeikov/ezrules/blob/main/LICENSE) for details
