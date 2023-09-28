.. ezrules documentation master file, created by
   sphinx-quickstart on Sun Sep 24 09:29:54 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to ezrules's documentation!
===================================

Ezrules is an open-source python package which aims to simplify business rule management and deployment for the fintech
industry. It is a one stop solution that includes the following components:

#. UI for Business Analysts for easy rule writing, testing and deployment
#. Multiple extendable storage backends for easy rule life-cycle management: create rules and review their modification history
#. Scalable rule execution engine
#. Backtesting capabilities

A simple script is availble to get a ready-to-go infrastructure in AWS.

In development:

#. Easy A/B testing of multiple rule configurations
#. Automated rule parameters adjustment

Deployment
==========
In order to deploy the infrastructure, from the root of the project run the following

.. code-block:: bash

   ./deployment/aws/deploy_stack.sh lambda_stack production
   ./deployment/aws/ezrule_app_stack.sh dynamodb_stack production
   ./deployment/aws/deploy_stack.sh ezrule_app_stack production

The first command deploys a lambda function responsible for running the generated rules. The second command deploys
a dynamodb table that serves as a storage backend. The last command deploys load balancers and ECS resources needed
for application serving.

Head over to `Load balancers AWS page <https://eu-west-1.console.aws.amazon.com/ec2/home?region=eu-west-1#LoadBalancers:>`_
(make sure a correct region is set) to see the deployed endpoints.

.. toctree::
   :maxdepth: 1
   :glob:
   :caption: Contents:

   docs/core/rule.rst
   docs/core/rule_engine.rst
   docs/core/rule_updater.rst



Indices and tables
==================


* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
