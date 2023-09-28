from abc import ABC, abstractmethod
import boto3
import json

class AbstractRuleExecutor(ABC):
    @abstractmethod
    def evaluate_rules(self, eval_object):
        """Evaluate object"""


class LambdaRuleExecutor(AbstractRuleExecutor):
    """Execute rule using an AWS Lambda function."""

    def __init__(self, fn_name: str) -> None:
        self.fn_name = fn_name
        self.client = boto3.client("lambda")

    def evaluate_rules(self, eval_object):
        response = self.client.invoke(
            FunctionName=self.fn_name,
            InvocationType="RequestResponse",  # Use 'RequestResponse' for synchronous invocation
            Payload=json.dumps(eval_object),
        )
        return json.loads(response["Payload"].read())
