.. _rule_logic:

Defining a Rule's Logic
######################

Introduction
************

The rules are written in a slightly modified version of Python. This means that you have the full power of Python when
writing a rule's logic, with its `if`, `then`, loops, and everything else.

Most of the time, a rule's logic will rely on transaction attributes to be compared either with each other
(think of comparing the current transaction volume versus the average weekly volume for the customer). In order to access
these attributes, the transaction information is available to you through an
object called ``t``, so you can look up the ``amount`` value by doing ``t["amount"]``.

Examples
********

Example 1 - react on transactions above certain value
=====================================================

.. code-block:: python

    if t["amount_usd"] > 500:
        return "HOLD"
    return "RELEASE"

Example 2 - this send is at least two times of standard deviation of weekly send
================================================================================

.. code-block:: python

    if t["amount"] > 2 * t["send_std_weekly"]:
        return "HOLD"
    return "RELEASE"

Example 3 - there are at least three small transactions within the past hour
============================================================================

.. code-block:: python

    small_count = 0
    for amount, tx_datetime in t["previous_transactions"]:
        time_difference = t["datetime"] - tx_datetime
        if time_difference < 3600:
            small_count = small_count + 1
        if small_count >= 3:
            return "HOLD"
    return "RELEASE"
