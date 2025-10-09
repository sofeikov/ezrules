ezrules Documentation
=====================

.. image:: https://img.shields.io/badge/python-3.12%2B-blue.svg
   :target: https://www.python.org/downloads/
   :alt: Python 3.12+

.. image:: https://readthedocs.org/projects/ezrules/badge/?version=latest
   :target: https://ezrules.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

**ezrules** is an open-source transaction monitoring engine that provides a comprehensive framework for defining, managing, and executing business rules with enterprise-grade security and scalability.

✨ Key Features
===============

🔧 **Rule Engine**
   Expressive Python-like language for writing business rules with intuitive syntax and real-time event processing.

🌐 **Web Management Interface**
   Flask-based UI for creating, testing, and managing business rules with intuitive workflows.

🔐 **Enterprise Security**
   Granular role-based access control with 13 permission types and complete audit trails for compliance.

📊 **Scalable Architecture**
   Multi-service deployment with dedicated manager and evaluator services for high-throughput environments.

🗄️ **Database Integration**
   PostgreSQL backend with SQLAlchemy ORM, full audit history, and change tracking.

🧪 **Backtesting**
   Test rule changes against historical data before deployment to validate business logic.

⚡ **Real-time Processing**
   High-performance rule evaluation with configurable outcomes and event-driven workflows.

🚀 Quick Start
==============

Get ezrules up and running in minutes:

Installation
------------

.. code-block:: bash

   # Clone and install
   git clone https://github.com/sofeikov/ezrules.git
   cd ezrules
   uv sync

Database Setup
--------------

.. code-block:: bash

   # Initialize database and permissions
   uv run ezrules init-db
   uv run ezrules init-permissions

   # Add your first user
   uv run ezrules add-user --user-email admin@example.com --password admin

Start Services
--------------

.. code-block:: bash

   # Start web interface (port 8888)
   uv run ezrules manager --port 8888

   # Start API service (port 9999)
   uv run ezrules evaluator --port 9999

Generate Test Data
------------------

.. code-block:: bash

   # Create sample rules and events
   uv run ezrules generate-random-data --n-rules 10 --n-events 100

🏗️ Architecture Overview
=========================

ezrules follows a service-oriented architecture designed for enterprise scalability:

**Core Components:**

* **Manager Service** - Web interface for rule management and monitoring (port 8888)
* **Evaluator Service** - REST API for real-time rule evaluation (port 9999)
* **Rule Engine** - Core logic for rule processing and outcome aggregation
* **Database Layer** - PostgreSQL with full audit history and change tracking

**Data Flow:**

1. Events submitted to evaluator service
2. Rules executed against event data using rule executors
3. Outcomes aggregated and stored with audit trail
4. Results available via API and web interface

🔐 Enterprise Security
======================

ezrules provides comprehensive security features for enterprise environments:

**Role-Based Access Control:**

* 13 granular permission types covering all system operations
* Pre-configured roles: Admin, Rule Editor, Read-only
* Resource-level permissions with department isolation
* Complete audit trail for compliance requirements

**Permission Categories:**

* **Rule Management** - Create, modify, delete, and view rules
* **Outcome Management** - Manage outcome types and configurations
* **List Management** - Control user lists and entries
* **Audit Access** - View system logs and change history

💼 Use Cases
============

ezrules excels in scenarios requiring automated decision-making:

**Financial Services**
   Real-time fraud detection, transaction monitoring, and compliance checking.

**Enterprise Compliance**
   Regulatory compliance with audit trails and role-based access control.

**Business Process Automation**
   Automated decision making based on configurable business logic.

**Event-Driven Systems**
   Rule-based responses to system events and data changes.

📚 Documentation Structure
==========================

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   usage/ui
   usage/rule_logic
   usage/executor

.. toctree::
   :maxdepth: 2
   :caption: Core Components

   core/rule_engine
   core/rule
   core/rule_updater

.. toctree::
   :maxdepth: 1
   :caption: Project Information

   whatsnew

🔗 Quick Links
==============

* **GitHub Repository**: https://github.com/sofeikov/ezrules
* **Issue Tracker**: https://github.com/sofeikov/ezrules/issues
* **Latest Release**: Check :ref:`whatsnew-label` for recent updates


Indices and tables
==================

* :ref:`whatsnew-label`
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
