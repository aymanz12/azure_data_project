# Databricks notebook source
# ============================================================
# Notebook : 02_silver_transform.py
# Layer    : SILVER  (Cleansed & Conformed layer)
# Purpose  : Read Bronze Delta tables, apply data quality
#            checks, cleanse, standardise and de-duplicate.
#            Write clean data to Silver Delta tables with SCD2.
# Author   : Data Engineering Team
# ============================================================

# COMMAND ----------
# MAGIC %md
# MAGIC # 🥈 Silver Layer — Cleanse & Conform
# MAGIC
# MAGIC **Medallion Architecture — Layer 2**
# MAGIC
# MAGIC | Property | Value |
# MAGIC |---|---|
# MAGIC | Input  | `bronze.*_raw` Delta tables |
# MAGIC | Output | `silver.*` Delta tables (clean, typed, SCD2) |
# MAGIC | DQ     | Null checks, type casting, dedup, referential integrity |
# MAGIC | Joins  | Enrich transactions with account + customer data |

# COMMAND ----------

from pyspark.sql import SparkSession, functions as F, Window
from pyspark.sql.types import *
from delta.tables import DeltaTable
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SilverTransform")

spark = SparkSession.builder \
    .appName("SilverTransform") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .getOrCreate()

# ── Parameters (injected by ADF / Databricks Jobs) ────────────────────────────
dbutils.widgets.text("bronze_path", "abfss://bronze@<ADLS>.dfs.core.windows.net/banking")
dbutils.widgets.text("silver_path", "abfss://silver@<ADLS>.dfs.core.windows.net/banking")
dbutils.widgets.text("run_date",    "2024-01-01")

BRONZE_PATH = dbutils.widgets.get("bronze_path")
SILVER_PATH = dbutils.widgets.get("silver_path")
RUN_DATE    = dbutils.widgets.get("run_date")

CATALOG   = "banking_catalog"
BRONZE_DB = "bronze"
SILVER_DB = "silver"

spark.sql(f"CREATE DATABASE IF NOT EXISTS {CATALOG}.{SILVER_DB}")
spark.sql(f"USE {CATALOG}.{SILVER_DB}")

# ── DQ Metrics Accumulator ────────────────────────────────────────────────────
dq_metrics = {}

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Silver: Transactions — Cleanse

# COMMAND ----------

raw_txn = spark.table(f"{CATALOG}.{BRONZE_DB}.transactions_raw") \
               .filter(F.col("_bronze_run_date") == RUN_DATE)

print(f"📥 Bronze transactions read: {raw_txn.count():,} rows")

# ── 1.1  Drop nulls in mandatory columns ─────────────────────────────────────
dq_metrics["txn_input_rows"] = raw_txn.count()

txn_no_nulls = raw_txn.filter(
    F.col("transaction_id").isNotNull() &
    F.col("account_id").isNotNull() &
    F.col("amount").isNotNull() &
    F.col("transaction_date").isNotNull()
)
dq_metrics["txn_nulls_dropped"] = dq_metrics["txn_input_rows"] - txn_no_nulls.count()
print(f"   Rows dropped (nulls in key cols): {dq_metrics['txn_nulls_dropped']:,}")

# ── 1.2  Remove duplicates on transaction_id ──────────────────────────────────
w_dedup = Window.partitionBy("transaction_id").orderBy(F.col("_bronze_ingested_at").desc())
txn_dedup = (
    txn_no_nulls
    .withColumn("_rank", F.row_number().over(w_dedup))
    .filter(F.col("_rank") == 1)
    .drop("_rank")
)
dq_metrics["txn_dupes_dropped"] = txn_no_nulls.count() - txn_dedup.count()
print(f"   Duplicates removed            : {dq_metrics['txn_dupes_dropped']:,}")

# ── 1.3  Type casting & standardisation ──────────────────────────────────────
txn_clean = (
    txn_dedup
    # Cast types
    .withColumn("amount",           F.col("amount").cast(DecimalType(18, 2)))
    .withColumn("transaction_date", F.to_timestamp("transaction_date", "yyyy-MM-dd HH:mm:ss"))
    .withColumn("is_flagged",       F.col("is_flagged").cast(BooleanType()))
    # Standardise strings
    .withColumn("currency",          F.upper(F.trim("currency")))
    .withColumn("transaction_type",  F.initcap(F.trim("transaction_type")))
    .withColumn("status",            F.initcap(F.trim("status")))
    .withColumn("channel",           F.initcap(F.trim("channel")))
    .withColumn("merchant_category", F.initcap(F.trim("merchant_category")))
    # Flag negative amounts
    .withColumn("amount_is_negative", F.col("amount") < 0)
    # Derived: transaction year/month for partitioning
    .withColumn("txn_year",  F.year("transaction_date"))
    .withColumn("txn_month", F.month("transaction_date"))
    # Remove invalid account_id (referential integrity — addressed after account silver is ready)
    .filter(F.col("account_id").rlike("^ACC[0-9]{8}$"))
    # Silver metadata
    .withColumn("_silver_processed_at", F.current_timestamp())
    .withColumn("_silver_run_date",     F.lit(RUN_DATE).cast(DateType()))
    .withColumn("_silver_version",      F.lit(1).cast(IntegerType()))
)

dq_metrics["txn_output_rows"] = txn_clean.count()
print(f"   Final clean rows              : {dq_metrics['txn_output_rows']:,}")

# ── 1.4  Write Silver — MERGE (upsert on transaction_id) ─────────────────────
silver_txn_path = f"{SILVER_PATH}/transactions"

if DeltaTable.isDeltaTable(spark, silver_txn_path):
    silver_txn = DeltaTable.forPath(spark, silver_txn_path)
    (
        silver_txn.alias("target")
        .merge(txn_clean.alias("source"), "target.transaction_id = source.transaction_id")
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
    print("✅  Silver transactions — MERGE done")
else:
    (
        txn_clean.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .partitionBy("txn_year", "txn_month")
        .save(silver_txn_path)
    )
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {CATALOG}.{SILVER_DB}.transactions
        USING DELTA LOCATION '{silver_txn_path}'
    """)
    print("✅  Silver transactions — initial write done")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Silver: Customers — Cleanse + SCD2

# COMMAND ----------

raw_cust = spark.table(f"{CATALOG}.{BRONZE_DB}.customers_raw")

dq_metrics["cust_input_rows"] = raw_cust.count()

# Dedup — keep latest record per customer_id
w_cust = Window.partitionBy("customer_id").orderBy(F.col("_bronze_ingested_at").desc())
cust_clean = (
    raw_cust
    .filter(F.col("customer_id").isNotNull())
    .withColumn("_rank", F.row_number().over(w_cust))
    .filter(F.col("_rank") == 1)
    .drop("_rank")
    .withColumn("credit_score",   F.col("credit_score").cast(IntegerType()))
    .withColumn("date_joined",    F.to_date("date_joined", "yyyy-MM-dd"))
    .withColumn("country",        F.upper(F.trim("country")))
    .withColumn("segment",        F.initcap(F.trim("segment")))
    .withColumn("email",          F.lower(F.trim("email")))
    .withColumn("is_active",      F.col("is_active").cast(BooleanType()))
    # SCD2 columns
    .withColumn("effective_start",  F.current_date())
    .withColumn("effective_end",    F.lit("9999-12-31").cast(DateType()))
    .withColumn("is_current",       F.lit(True))
    .withColumn("_silver_processed_at", F.current_timestamp())
)

dq_metrics["cust_output_rows"] = cust_clean.count()

(
    cust_clean.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.{SILVER_DB}.customers")
)
print(f"✅  Silver customers → {dq_metrics['cust_output_rows']:,} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Silver: Accounts — Cleanse

# COMMAND ----------

raw_acc = spark.table(f"{CATALOG}.{BRONZE_DB}.accounts_raw")

acc_clean = (
    raw_acc
    .filter(F.col("account_id").isNotNull() & F.col("customer_id").isNotNull())
    .withColumn("balance",         F.col("balance").cast(DecimalType(18, 2)))
    .withColumn("open_date",       F.to_date("open_date", "yyyy-MM-dd"))
    .withColumn("account_type",    F.initcap(F.trim("account_type")))
    .withColumn("account_status",  F.initcap(F.trim("account_status")))
    .withColumn("currency",        F.upper(F.trim("currency")))
    # Flag suspicious negative balances
    .withColumn("balance_flag",    F.when(F.col("balance") < 0, "NEGATIVE").otherwise("NORMAL"))
    .withColumn("_silver_processed_at", F.current_timestamp())
)

(
    acc_clean.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.{SILVER_DB}.accounts")
)
print(f"✅  Silver accounts → {acc_clean.count():,} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Silver: Fraud Labels — Join & Enrich

# COMMAND ----------

raw_fraud = spark.table(f"{CATALOG}.{BRONZE_DB}.fraud_labels_raw")
silver_txn_df = spark.table(f"{CATALOG}.{SILVER_DB}.transactions")

fraud_enriched = (
    raw_fraud
    .filter(F.col("transaction_id").isNotNull())
    .join(
        silver_txn_df.select("transaction_id", "account_id", "amount", "transaction_date"),
        on="transaction_id",
        how="left"
    )
    .withColumn("review_date",  F.to_date("review_date", "yyyy-MM-dd"))
    .withColumn("fraud_label",  F.initcap(F.trim("fraud_label")))
    .withColumn("_silver_processed_at", F.current_timestamp())
)

(
    fraud_enriched.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.{SILVER_DB}.fraud_labels")
)
print(f"✅  Silver fraud_labels → {fraud_enriched.count():,} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Silver Summary & DQ Report

# COMMAND ----------

silver_tables = {
    "transactions" : f"{CATALOG}.{SILVER_DB}.transactions",
    "customers"    : f"{CATALOG}.{SILVER_DB}.customers",
    "accounts"     : f"{CATALOG}.{SILVER_DB}.accounts",
    "fraud_labels" : f"{CATALOG}.{SILVER_DB}.fraud_labels",
}

print("\n" + "="*65)
print("  🥈 SILVER LAYER — TRANSFORMATION SUMMARY")
print("="*65)
for name, tbl in silver_tables.items():
    count = spark.sql(f"SELECT COUNT(*) AS cnt FROM {tbl}").collect()[0]["cnt"]
    print(f"   {name:<25} {count:>10,} rows")

print("\n  📊 Data Quality Metrics:")
for k, v in dq_metrics.items():
    print(f"     {k:<30} {v:>10,}")

print("="*65)
print(f"   Run date: {RUN_DATE}  |  Status: ✅ COMPLETE")
