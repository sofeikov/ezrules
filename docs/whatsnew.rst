.. _whatsnew-label:

What's new
----------

v0.3

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