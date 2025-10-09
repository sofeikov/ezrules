# Welcome to ezrules

**Open-source transaction monitoring engine for business rules**

ezrules provides a Python-based framework for defining, managing, and executing business rules with a web-based management interface and scalable infrastructure for rule execution and backtesting.

---

## What is ezrules?

ezrules is designed for organizations that need to monitor transactions, detect fraud, and enforce business logic at scale. Whether you're building a financial compliance system, automating business decisions, or analyzing transaction patterns, ezrules provides the tools you need.

### Key Capabilities

- **Flexible Rule Engine** - Write business rules in a Python-like language with expressive syntax for transaction logic
- **Web Management Interface** - Create and manage rules through an intuitive web UI
- **Enterprise Security** - Granular role-based access control with 13 permission types
- **Transaction Labeling** - Comprehensive fraud analytics with API and bulk CSV upload
- **Analytics Dashboard** - Real-time monitoring with configurable time ranges
- **Audit Trail** - Complete change tracking for compliance and regulatory requirements

---

## Quick Links

<div class="grid cards" markdown>

-   :material-clock-fast:{ .lg .middle } __Quick Start__

    ---

    Get up and running in minutes with our quick start guide

    [:octicons-arrow-right-24: Quick Start](getting-started/quickstart.md)

-   :material-book-open-variant:{ .lg .middle } __User Guides__

    ---

    Learn how to use ezrules for your role - analyst, admin, or developer

    [:octicons-arrow-right-24: Guides](user-guide/analyst-guide.md)

-   :material-api:{ .lg .middle } __API Reference__

    ---

    Integrate ezrules with your applications using our REST APIs

    [:octicons-arrow-right-24: API Docs](api-reference/evaluator-api.md)

-   :material-architecture:{ .lg .middle } __Architecture__

    ---

    Understand how ezrules works under the hood

    [:octicons-arrow-right-24: Architecture](architecture/overview.md)

</div>

---

## Use Cases

### Financial Transaction Monitoring
Real-time fraud detection and compliance checking with configurable rules and immediate alerting.

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
| **Web Interface** | Flask-based UI for rule creation and management |
| **API Service** | Dedicated evaluator service for real-time rule execution |
| **Security** | 13 permission types with role-based access control |
| **Labeling** | API and bulk CSV upload for transaction labels |
| **Analytics** | Time-series charts with 1h, 6h, 12h, 24h, 30d ranges |
| **Database** | PostgreSQL backend with SQLAlchemy ORM |
| **Audit Trail** | Complete history of all changes and access |
| **Backtesting** | Test rule changes against historical data |
| **CLI Tools** | Command-line interface for operations and testing |

---

## Architecture Overview

ezrules uses a multi-service architecture for scalability and flexibility:

```
┌─────────────────┐
│   Web Browser   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Manager Service│────▶│    PostgreSQL   │
│   (Port 8888)   │     │    Database     │
└─────────────────┘     └─────────────────┘
                               ▲
                               │
┌─────────────────┐            │
│ External Apps   │            │
└────────┬────────┘            │
         │                     │
         ▼                     │
┌─────────────────┐            │
│ Evaluator Service│───────────┘
│   (Port 9999)   │
└─────────────────┘
```

- **Manager Service**: Web UI for rule management and monitoring
- **Evaluator Service**: REST API for real-time rule evaluation
- **Database**: Central storage for rules, events, and analytics
- **Celery Workers**: Background task processing for rule backtesting

---

## Getting Started

Ready to start using ezrules? Follow our installation guide:

[Get Started →](getting-started/installation.md){ .md-button .md-button--primary }

Or jump straight to a practical example:

[Quick Start →](getting-started/quickstart.md){ .md-button }

---

## Community & Support

- **GitHub**: [sofeikov/ezrules](https://github.com/sofeikov/ezrules)
- **Issues**: Report bugs or request features on [GitHub Issues](https://github.com/sofeikov/ezrules/issues)
- **License**: MIT License - see [LICENSE](https://github.com/sofeikov/ezrules/blob/main/LICENSE) for details
