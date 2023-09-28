This page describes the objects that help to manage the lifecycle of a rule. It contains a core definition for an abstract
class :class:`core.rule_updater.RuleManager`, as well two examples(:class:`core.rule_updater.FSRuleManager` and :class:`core.rule_updater.DynamoDBRuleManager`) implementations
to illustrate the design principles behind
the abstract class.

.. autoclass:: core.rule_updater.RuleManager
   :members:
   :private-members:
   :undoc-members:

.. autoclass:: core.rule_updater.FSRuleManager
   :members:
   :private-members:
   :special-members: __init__
   :undoc-members:

.. autoclass:: core.rule_updater.DynamoDBRuleManager
   :members:
   :private-members:
   :special-members: __init__
   :undoc-members:

Below are auxiliary objects that can be used in specific implementations.
.. note::

   `RULE_MANAGERS` is a dictionary that maps string keys to corresponding Rule Manager classes. It is used to identify and instantiate different types of Rule Managers based on string keys.

   Example::

       RULE_MANAGERS = {
           "FSRuleManager": FSRuleManager,
           "DynamoDBRuleManager": DynamoDBRuleManager,
       }

In order to add a new implementation, import the dictionary and change it inplace.

.. autofunction:: core.rule_updater.calculate_md5

.. autoexception:: core.rule_updater.UnableToLockStorageException

.. autoexception:: core.rule_updater.RuleDoesNotExistInTheStorage