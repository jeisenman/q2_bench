# Databricks notebook source
# MAGIC %md
# MAGIC # Remote data query: pl-databricks-us-rapreprod-01
# MAGIC Generated query boilerplate. Review before running.

# COMMAND ----------

import json
import platform
import pandas as pd
from pyspark.sql import functions as F
values = [-1.0, 0.0, 1.0, None]
pandas_output = pd.DataFrame({'value': values}).query('value > 0')['value'].tolist()
spark_output = [row.value for row in spark.createDataFrame([(value,) for value in values], 'value double').where(F.col('value') > 0).collect()]
assert pandas_output == [1.0]
assert spark_output == [1.0]
dbutils.notebook.exit(json.dumps({'format': 'q2-formal-lineage-ra-probe/v1', 'synthetic_only': True, 'python': platform.python_version(), 'pandas': pd.__version__, 'spark': spark.version, 'input': values, 'pandas_output': pandas_output, 'spark_output': spark_output, 'passed': True}))
