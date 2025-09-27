.. _whatsnew-label:

What's new
----------
v0.9
* Implementation of RBAC: per-resource access control, audit trail
* List and outcomes are now editable

v0.7

* Migrated from Poetry to UV for faster dependency management
* Upgraded to Python 3.12 minimum requirement

v0.6

* Ability to backtest rule changes: make change, submit for backtesing, check result
* Switch to pydantic-based settings management
* Transaction submitted for testing are now saved in the history table
* Rule evaluation results are now saved in the history table
* new cli utilities to generate test data

v0.5

* The app is compatible with AWS EKS
* Basic testing introduced
* Rule history is maintained through a history table
* Standalone scripts to init the db and add a user
* Internall, switch to poetry dependancy management
* Manager and evaluator can run as executables

v0.5

* RDBMS are now supported as a backend for rule configuration storage
* The application can now be deployed in a k8s cluster

v0.4

* At-notation is available. Constructs of type `if $send_country in @Latam...`
* Users are now required to login to make changes to the rule set


v0.3

* Dollar-notation can be used to refer to attributes, e.g. `if $amount>1000...`
* When you create a rule, you can now test it right away before deploying
* Outcomes of rules are now controlled against a list of allowed outcomes
* When a rule is edited, there is now a warning that someone else is working on it too
* Each rule revision now has a timestamp associated with it
* For rules with modification history, see the changelog with highlighted diffs

v0.2

* A better documentation on rules writing
* Fixed a bug wherein the lambda rule executor was not properly configured with the environment variable
* Rule evaluator app now accepts lambda function name through an environment variable
* Rule manager fetched the s3 bucket name from an environment variable now
* Rule manager backend table name is now automatically configured with `DYNAMODB_RULE_MANAGER_TABLE_NAME` environment variable
* General code cleanup

v0.1

* A single script that deploys application to AWS
* This is a first release, so all previous changes are squashed into it