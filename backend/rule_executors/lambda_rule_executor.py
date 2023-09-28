import os
import s3fs
import boto3
from urllib.parse import urlparse
from core.rule_engine import RuleEngineFactory

s3 = s3fs.S3FileSystem()
s3client = boto3.client("s3")
CURRENT_RULES_ETAG = ""
RULE_ENGINER_YAML_PATH = os.environ["RULE_ENGINE_YAML_PATH"]
RULE_ENGINE = RuleEngineFactory.from_yaml(RULE_ENGINER_YAML_PATH)


def ensure_latest_etag():
    global CURRENT_RULES_ETAG
    global RULE_ENGINE
    o = urlparse(RULE_ENGINER_YAML_PATH)
    obtained_etag = s3client.get_object_attributes(
        Bucket=o.netloc, Key=o.path[1:], ObjectAttributes=["ETag"]
    )["ETag"]
    if obtained_etag != CURRENT_RULES_ETAG:
        print(
            f"Etags do not match: {obtained_etag}(freshly checked) vs {CURRENT_RULES_ETAG}(currently assumed); Downloading rules."
        )
        RULE_ENGINE = RuleEngineFactory.from_yaml(RULE_ENGINER_YAML_PATH)
        CURRENT_RULES_ETAG = obtained_etag


def lambda_handler(event, context):
    ensure_latest_etag()
    response = RULE_ENGINE(event)
    return response


if __name__ == "__main__":
    print(lambda_handler({"send_country": "US", "score": 500}, None))
