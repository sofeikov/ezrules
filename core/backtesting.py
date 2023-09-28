from pyspark.sql import SparkSession
from pyspark.sql import Row
from core.rule_engine import RuleEngineFactory
from pyspark.sql.functions import udf, struct
from pyspark.sql.types import StringType
import json

rule_engine = RuleEngineFactory.from_yaml("rule-config.yaml")


def apply_rule_engine(row):
    row = row.asDict()
    res = rule_engine(row)
    return json.dumps(res)


udf_apply_rule_engine = udf(apply_rule_engine, StringType())

spark = SparkSession.builder.getOrCreate()

df = spark.createDataFrame(
    [
        Row(send_country="US", score=951),
        Row(send_country="US", score=440),
    ],
    schema="send_country string, score int",
)

df.withColumn("res", udf_apply_rule_engine(struct([df[x] for x in df.columns]))).show()
