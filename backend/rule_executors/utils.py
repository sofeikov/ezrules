import os
from typing import Optional, Tuple, Any
from urllib.parse import urlparse

import boto3
import s3fs

from core.rule_engine import RuleEngine, RuleEngineFactory


s3 = s3fs.S3FileSystem()
s3client = boto3.client("s3")


def ensure_latest_etag(
    rule_engine_yaml_path: str,
    current_rules_etag: Optional[str] = None,
) -> tuple[Optional[RuleEngine], str]:
    o = urlparse(rule_engine_yaml_path)
    obtained_etag = s3client.get_object_attributes(
        Bucket=o.netloc, Key=o.path[1:], ObjectAttributes=["ETag"]
    )["ETag"]
    if obtained_etag != current_rules_etag:
        print(
            f"Etags do not match: {obtained_etag}(freshly checked) vs {current_rules_etag}(currently assumed); Downloading rules."
        )
        return RuleEngineFactory.from_yaml(rule_engine_yaml_path), obtained_etag
    return None, obtained_etag
