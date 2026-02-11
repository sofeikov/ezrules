# What's New

## v0.11

* **Frontend authentication**: The Angular frontend now has full JWT authentication. Users must log in with email/password before accessing any page. Includes a login page, automatic token refresh, HTTP interceptor for attaching tokens to API requests, route guards that redirect unauthenticated users to login, and a Sign Out button in the sidebar. E2E tests use Playwright's global setup to authenticate once and share auth state across all tests.
* **Flask removal**: The legacy Flask manager service (`ezrules manager`) has been fully removed. The Angular frontend with FastAPI API v2 is now the sole interface.
* **Removed CLI commands**: `ezrules manager` and `ezrules evaluator` commands have been removed. Use `ezrules api` to start the service.
* **Removed dependencies**: Flask, Flask-Security-Too, Flask-WTF, Flask-CORS, Bootstrap-Flask, and pytz have been removed from the project dependencies. Gunicorn is retained for production deployments with uvicorn workers.
* **Standalone model mixins**: `AsaList`, `RoleMixin`, and `UserMixin` previously imported from flask_security are now defined directly in `ezrules.models.backend_core`, removing the flask_security dependency from the data model layer.
* **Removed Flask decorator**: The `requires_permission` Flask decorator in `ezrules.core.permissions` has been removed. The FastAPI API v2 uses its own `require_permission` dependency in `ezrules.backend.api_v2.auth.dependencies`.
* **Explicit versioning**: Replaced `history_meta.py` auto-versioning system with explicit `RuleHistory` and `RuleEngineConfigHistory` models. History snapshots are now created by helper functions (`save_rule_history`, `save_config_history`) before mutations, giving full control over when and how history is recorded.
* **Changed-by tracking**: Rule and configuration history entries now include a `changed_by` column that records who made each change (user email from API, `"cli"` from CLI commands). The Audit Trail page in the Angular frontend displays this in a new "Changed By" column.
* **Removed history_meta.py**: The SQLAlchemy event-listener-based `history_meta.py` module and all `versioned_session()` calls have been removed. Database tables must be recreated with `uv run ezrules init-db --auto-delete`.
* **Enhanced audit trail**: The audit trail now tracks changes to user lists (create, rename, delete, add/remove entries), outcomes (create, delete), and labels (create, delete) in addition to rules and configurations. Each audit entry records who performed the action and when. New API endpoints: `GET /api/v2/audit/user-lists`, `GET /api/v2/audit/outcomes`, `GET /api/v2/audit/labels`.
* **Accordion audit page**: The Audit Trail page has been redesigned with collapsible accordion sections for Rule History, Configuration History, User List History, Outcome History, and Label History. Sections are collapsed by default to reduce visual clutter. Action types are shown with color-coded badges (green for creates, red for deletes, blue for renames).

## v0.10

* **FastAPI Migration (In Progress)**: New API v2 service built on FastAPI for improved performance and modern async support
* **Evaluator merged into API service**: The standalone evaluator service (port 9999) has been merged into the main API service. Rule evaluation is now available at `/api/v2/evaluate` on port 8888. The `evaluator` CLI command is deprecated in favour of `api`.
* New CLI command `uv run ezrules api --port 8888` to start FastAPI server with optional `--reload` flag for development
* JWT authentication system (coming soon) - will support both local users and future OAuth/SSO integrations
* OpenAPI documentation automatically available at `/docs` (Swagger UI) and `/redoc`
* CORS configured for Angular development server (localhost:4200)
* **User Lists management page**: Angular frontend page for managing user lists and their entries. Accessible from the sidebar, supports creating/deleting lists, adding/removing entries with a master-detail layout. Backend API at `/api/v2/user-lists/`.
* **Database initialisation seeds default data**: `uv run ezrules init-db` now seeds default outcomes (RELEASE, HOLD, CANCEL) and default user lists (MiddleAsiaCountries, NACountries, LatamCountries) so rules using `@ListName` notation work out of the box.
* **Rule test endpoint accepts string outcomes**: The rule test endpoint (`POST /api/v2/rules/test`) now correctly handles rules that return string outcomes like `"HOLD"`, not just booleans.
* **Dashboard page**: Angular dashboard showing active rules count, transaction volume chart, and rule outcomes over time charts. Includes time range selector (1h, 6h, 12h, 24h, 30d). Accessible from sidebar and is the default landing page.
* **User Management admin panel**: Angular page at `/management/users` for managing user accounts. Supports creating users with optional role assignment, deleting users, toggling active/inactive status, admin-initiated password reset, and inline role assignment/removal. Accessible from sidebar "Security" link.
* **Role Management page**: Angular page at `/role_management` for managing roles. Supports creating roles with descriptions, assigning roles to users via dropdowns, removing roles from users, deleting roles (only when no users assigned), and links to per-role permission configuration. Accessible from sidebar "Settings" link.
* **Role Permissions page**: Angular page at `/role_management/{id}/permissions` for configuring per-role permissions. Displays all available permissions grouped by resource type with checkboxes, shows current permissions as green summary badges, and supports saving permission changes. Navigable from the Role Management page via "Manage Permissions" link.
* **Audit Trail page**: Angular page at `/audit` showing the history of rule and configuration changes. Displays two tables: Rule History (version, rule ID, description truncated to 100 chars, changed timestamp) and Configuration History (version, label, changed timestamp), each sorted by date descending. Accessible from the sidebar.

## v0.9

* Implementation of RBAC: per-resource access control, audit trail
* List and outcomes are now editable
* User management UI
* Role and permissions management UI
* Enhanced init-db script with interactive database management and --auto-delete option
* Transaction marking for analytics: mark transactions with true labels for fraud detection analysis
* Single event marking API endpoint (/mark-event) for programmatic labeling
* Bulk CSV upload interface for efficient batch labeling of events
* Enhanced CLI test data generation with realistic fraud patterns and label assignment
* Automatic default label creation (FRAUD, CHARGEBACK, NORMAL) for immediate testing
* Dashboard transaction volume chart with Chart.js: visualize transaction patterns over configurable time ranges
* Time aggregation options: 1 hour, 6 hours, 12 hours, 24 hours, and 30 days
* Real-time API endpoint for transaction volume data (/api/transaction_volume)
* **Label Analytics Dashboard**: Comprehensive analytics for ground truth labels with temporal analysis
* Total labeled events metric card tracking overall labeling coverage
* Individual time-series charts for each label type showing temporal trends over configurable time ranges
* Label analytics API endpoints: /api/labels_summary, /api/labels_distribution
* Configurable time ranges for label analytics (1h, 6h, 12h, 24h, 30d)
* Angular frontend revision navigation: clicking a rule revision link now navigates to a read-only view of that historical revision via GET /api/rules/<id>/revisions/<rev>
* **Outcomes management page**: Ported to Angular frontend. Users can list, create, and delete allowed outcomes via the new /outcomes page, reachable from the sidebar. Backend API endpoints added: GET/POST /api/outcomes, DELETE /api/outcomes/<name>
* **Label Analytics page ported to Angular frontend**: The /label_analytics page is now available in the Angular app, reachable via the sidebar "Analytics" link. Displays the total labeled events metric card and per-label time-series line charts powered by Chart.js, with a time range selector (1h, 6h, 12h, 24h, 30d) that updates charts in real time

## v0.7

* Migrated from Poetry to UV for faster dependency management
* Upgraded to Python 3.12 minimum requirement

## v0.6

* Ability to backtest rule changes: make change, submit for backtesting, check result
* Switch to pydantic-based settings management
* Transaction submitted for testing are now saved in the history table
* Rule evaluation results are now saved in the history table
* New CLI utilities to generate test data

## v0.5

* The app is compatible with AWS EKS
* Basic testing introduced
* Rule history is maintained through a history table
* Standalone scripts to init the db and add a user
* Internally, switch to poetry dependency management
* Manager and evaluator can run as executables

## v0.4

* RDBMS are now supported as a backend for rule configuration storage
* The application can now be deployed in a k8s cluster

## v0.3

* At-notation is available. Constructs of type `if $send_country in @Latam...`
* Users are now required to login to make changes to the rule set

## v0.2

* Dollar-notation can be used to refer to attributes, e.g. `if $amount>1000...`
* When you create a rule, you can now test it right away before deploying
* Outcomes of rules are now controlled against a list of allowed outcomes
* When a rule is edited, there is now a warning that someone else is working on it too
* Each rule revision now has a timestamp associated with it
* For rules with modification history, see the changelog with highlighted diffs

## v0.1

* A better documentation on rules writing
* Fixed a bug wherein the lambda rule executor was not properly configured with the environment variable
* Rule evaluator app now accepts lambda function name through an environment variable
* Rule manager fetched the s3 bucket name from an environment variable now
* Rule manager backend table name is now automatically configured with `DYNAMODB_RULE_MANAGER_TABLE_NAME` environment variable
* General code cleanup

## v0.0

* A single script that deploys application to AWS
* This is a first release, so all previous changes are squashed into it
