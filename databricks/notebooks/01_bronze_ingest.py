# Databricks notebook source
# ============================================================
# Notebook : 01_bronze_ingest.py
# Layer    : BRONZE  (Raw ingestion layer)
# Purpose  : Read raw CSVs that ADF copied to ADLS Gen2 and
#            write them as Delta tables in the Bronze container.
#            Minimal transformation — only add metadata columns.
# Author   : Data Engineering Team
# ============================================================

# COMMAND ----------
# MAGIC %md
# MAGIC # 🥉 Bronze Layer — Raw Ingestion
# MAGIC
# MAGIC **Medallion Architecture — Layer 1**
# MAGIC
# MAGIC | Property | Value |
# MAGIC |---|---|
# MAGIC | Input  | ADLS Parquet files (ADF-copied from Blob) |
# MAGIC | Output | Delta tables in `bronze` database |
# MAGIC | Schema | Schema-on-read (raw, no transformations) |
# MAGIC | Goal   | Immutable, auditable raw data landing zone |

# COMMAND ----------

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *
from delta.tables import DeltaTable
from datetime import datetime

# Initialise Spark (already available in Databricks — this is for clarity)
spark = SparkSession.builder.appName("BronzeIngestion").getOrCreate()

# ── Configuration ─────────────────────────────────────────────────────────────
# In Databricks, these would come from:
#   - ADF pipeline parameters (dbutils.widgets)
#   - Azure Key Vault-backed secrets (dbutils.secrets)

dbutils.widgets.text("bronze_path", "abfss://bronze@<ADLS>.dfs.core.windows.net/banking")
dbutils.widgets.text("run_date",    "2024-01-01")

BRONZE_PATH = dbutils.widgets.get("bronze_path")
RUN_DATE    = dbutils.widgets.get("run_date")

CATALOG   = "banking_catalog"     # Unity Catalog
BRONZE_DB = "bronze"

# Create database if not exists
spark.sql(f"CREATE DATABASE IF NOT EXISTS {CATALOG}.{BRONZE_DB}")
spark.sql(f"USE {CATALOG}.{BRONZE_DB}")

print(f"✅ Bronze database ready: {CATALOG}.{BRONZE_DB}")
print(f"   Run date  : {RUN_DATE}")
print(f"   Input path: {BRONZE_PATH}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1.  Helper: Add Bronze metadata columns

# COMMAND ----------

def add_bronze_metadata(df, source_name: str):
    """
    Adds standard audit/lineage columns to every Bronze table.
    These columns are NEVER modified in downstream layers.
    """
    return df \
        .withColumn("_bronze_ingested_at",  F.current_timestamp()) \
        .withColumn("_bronze_source_file",  F.input_file_name()) \
        .withColumn("_bronze_run_date",     F.lit(RUN_DATE).cast(DateType())) \
        .withColumn("_bronze_pipeline",     F.lit("PL_Ingest_Banking_Raw_To_Bronze")) \
        .withColumn("_bronze_source_name",  F.lit(source_name)) \
        .withColumn("_bronze_is_deleted",   F.lit(False))        # SCD support

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Ingest Transactions

# COMMAND ----------

print("📥 Reading transactions Parquet from ADLS Bronze...")

transactions_raw = (
    spark.read
    .format("parquet")
    .option("mergeSchema", "true")
    .load(f"{BRONZE_PATH}/transactions/{RUN_DATE.replace('-', '/')}/")
)

transactions_bronze = add_bronze_metadata(transactions_raw, "blob/banking/transactions")

print(f"   Rows read: {transactions_raw.count():,}")
transactions_bronze.printSchema()

# Write as Delta table (append mode — Bronze is append-only)
(
    transactions_bronze.write
    .format("delta")
    .mode("append")
    .option("mergeSchema", "true")
    .partitionBy("_bronze_run_date")
    .saveAsTable(f"{CATALOG}.{BRONZE_DB}.transactions_raw")
)
print("✅  transactions_raw written to Bronze Delta table")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Ingest Customers

# COMMAND ----------

customers_raw    = spark.read.format("parquet").load(f"{BRONZE_PATH}/customers/")
customers_bronze = add_bronze_metadata(customers_raw, "blob/banking/customers")

(
    customers_bronze.write
    .format("delta")
    .mode("append")
    .option("mergeSchema", "true")
    .partitionBy("_bronze_run_date")
    .saveAsTable(f"{CATALOG}.{BRONZE_DB}.customers_raw")
)
print(f"✅  customers_raw  → {customers_raw.count():,} rows written")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Ingest Accounts

# COMMAND ----------

accounts_raw    = spark.read.format("parquet").load(f"{BRONZE_PATH}/accounts/")
accounts_bronze = add_bronze_metadata(accounts_raw, "blob/banking/accounts")

(
    accounts_bronze.write
    .format("delta")
    .mode("append")
    .option("mergeSchema", "true")
    .partitionBy("_bronze_run_date")
    .saveAsTable(f"{CATALOG}.{BRONZE_DB}.accounts_raw")
)
print(f"✅  accounts_raw   → {accounts_raw.count():,} rows written")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Ingest Fraud Labels

# COMMAND ----------

fraud_raw    = spark.read.format("parquet").load(f"{BRONZE_PATH}/fraud_labels/")
fraud_bronze = add_bronze_metadata(fraud_raw, "blob/banking/fraud_labels")

(
    fraud_bronze.write
    .format("delta")
    .mode("append")
    .option("mergeSchema", "true")
    .partitionBy("_bronze_run_date")
    .saveAsTable(f"{CATALOG}.{BRONZE_DB}.fraud_labels_raw")
)
print(f"✅  fraud_labels_raw → {fraud_raw.count():,} rows written")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Bronze Summary Report

# COMMAND ----------

bronze_tables = ["transactions_raw", "customers_raw", "accounts_raw", "fraud_labels_raw"]

print("\n" + "="*60)
print("  🥉 BRONZE LAYER — INGESTION SUMMARY")
print("="*60)
for t in bronze_tables:
    count = spark.sql(f"SELECT COUNT(*) AS cnt FROM {CATALOG}.{BRONZE_DB}.{t}").collect()[0]["cnt"]
    print(f"   {t:<30} {count:>10,} total rows")

print("="*60)
print(f"   Run date: {RUN_DATE}  |  Status: ✅ COMPLETE")
