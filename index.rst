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

   ./deployment/aws/deploy_all.sh environment_name

This command will do the following:

#. Create a bucket that will be used by the application
#. Package and upload lambda function code
#. Deploy a lambda function that will execute the business logic
#. Create UI application for analysts

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
