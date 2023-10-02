.. _usage-label:

Using the UI to create business rules
=====================================

UI description
**************

Once the application is deployed and :ref:`load balancers <deployed_load_balancers>` become availble, open the UI load
balancer and you will be presented with the following interface:

.. image:: https://ezrules-docs-images.s3.eu-west-2.amazonaws.com/empty-rule-list.png
    :alt: Empty rule list

Clicking ``Add rule`` brings up the following interface:

.. image:: https://ezrules-docs-images.s3.eu-west-2.amazonaws.com/new-rule-ui.png
    :alt: New rule interface

In this interface:

* ``A unique rule ID`` - a unique rule name. Once a rule is created, the ID can not be changed and is used through the entire rule lifecycle.
* ``Rule description`` - a human readable rule description that helps to understand what the rule is trying to achieve.
* ``Rule logic`` - how exactly rule achieves what's stated in the description. Refer to :ref:`Rule logic definition <rule_logic>` for more info.
* ``Rule tags`` and ``Rule params`` are currently unused.

First rule
**********

Let's write a rule that goes like this: if the transaction amount is higher than 900, and the risk score is higher than 300,
then we ``HOLD`` it, otherwise we ``RELEASE`` it. This would look something like this:

.. image:: https://ezrules-docs-images.s3.eu-west-2.amazonaws.com/new-rule-config-example.png
    :alt: New rule interface

Now, in the list of rules, there is a new entry:

.. image:: https://ezrules-docs-images.s3.eu-west-2.amazonaws.com/new-rule-in-the-list.png
    :alt: New rule interface

Executing the new rule
**********************

See the :ref:`executor API description <executor_api>` for more details.

In order to execute the new rule, we can use the following ``curl`` command::

    curl -X POST -H "Content-Type: application/json" -d '{"amount": 950, "risk_score": 100}' <your load balancer DNS name>/evaluate

which should return::

    ["RELEASE"]

Trying to submit a higher risk score would result in ``HOLD`` returned::

    curl -X POST -H "Content-Type: application/json" -d '{"amount": 950, "risk_score": 600}' <your load balancer DNS name>/evaluate

returns::

    ["HOLD"]
