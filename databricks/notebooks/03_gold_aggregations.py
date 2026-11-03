# Databricks notebook source
# ============================================================
# Notebook : 03_gold_aggregations.py
# Layer    : GOLD  (Business-ready, analytics layer)
# Purpose  : Build curated, aggregated fact and dimension
#            tables that feed Power BI dashboards directly.
#            All Gold tables are optimised for BI consumption.
# Author   : Data Engineering Team
# ============================================================

# COMMAND ----------
# MAGIC %md
# MAGIC # 🥇 Gold Layer — Business-Ready Aggregations
# MAGIC
# MAGIC **Medallion Architecture — Layer 3**
# MAGIC
# MAGIC | Property | Value |
# MAGIC |---|---|
# MAGIC | Input   | `silver.*` Delta tables |
# MAGIC | Output  | `gold.*` Delta tables |
# MAGIC | Purpose | Business KPIs, dashboards, ML feature store |
# MAGIC | Consumers | Power BI, Azure Synapse Analytics, ML models |
# MAGIC
# MAGIC **Gold Tables produced:**
# MAGIC | Table | Description |
# MAGIC |---|---|
# MAGIC | `gold.fact_transactions`        | Enriched transaction fact table |
# MAGIC | `gold.dim_customers`            | Customer dimension (current view) |
# MAGIC | `gold.dim_accounts`             | Account dimension |
# MAGIC | `gold.agg_daily_txn_summary`    | Daily transaction KPIs |
# MAGIC | `gold.agg_customer_360`         | Customer 360 view |
# MAGIC | `gold.agg_fraud_analysis`       | Fraud detection summary |
# MAGIC | `gold.agg_channel_performance`  | Channel breakdown |
# MAGIC | `gold.agg_merchant_insights`    | Merchant category spend |

# COMMAND ----------

from pyspark.sql import SparkSession, functions as F, Window
from pyspark.sql.types import *
from delta.tables import DeltaTable

spark = SparkSession.builder.appName("GoldAggregations").getOrCreate()

dbutils.widgets.text("silver_path", "abfss://silver@<ADLS>.dfs.core.windows.net/banking")
dbutils.widgets.text("gold_path",   "abfss://gold@<ADLS>.dfs.core.windows.net/banking")
dbutils.widgets.text("run_date",    "2024-01-01")

SILVER_PATH = dbutils.widgets.get("silver_path")
GOLD_PATH   = dbutils.widgets.get("gold_path")
RUN_DATE    = dbutils.widgets.get("run_date")

CATALOG   = "banking_catalog"
SILVER_DB = "silver"
GOLD_DB   = "gold"

spark.sql(f"CREATE DATABASE IF NOT EXISTS {CATALOG}.{GOLD_DB}")

# ── Load Silver tables ─────────────────────────────────────────────────────────
silver_txn    = spark.table(f"{CATALOG}.{SILVER_DB}.transactions")
silver_cust   = spark.table(f"{CATALOG}.{SILVER_DB}.customers")
silver_acc    = spark.table(f"{CATALOG}.{SILVER_DB}.accounts")
silver_fraud  = spark.table(f"{CATALOG}.{SILVER_DB}.fraud_labels")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Gold: Fact Transactions (Enriched)

# COMMAND ----------

fact_transactions = (
    silver_txn.alias("t")
    # Join with Accounts
    .join(
        silver_acc.alias("a").select(
            "account_id", "customer_id", "account_type", "account_status",
            "currency", "branch_code", "balance"
        ),
        on="account_id", how="left"
    )
    # Join with Customers
    .join(
        silver_cust.alias("c").select(
            "customer_id", "first_name", "last_name",
            "country", "segment", "credit_score"
        ),
        on="customer_id", how="left"
    )
    # Join with Fraud labels
    .join(
        silver_fraud.select("transaction_id", "fraud_label", "reviewed_by"),
        on="transaction_id", how="left"
    )
    # Derived business fields
    .withColumn("full_name",       F.concat_ws(" ", "first_name", "last_name"))
    .withColumn("fraud_label",     F.coalesce(F.col("fraud_label"), F.lit("Clean")))
    .withColumn("is_fraud",        F.col("fraud_label").isin(["Confirmed", "Suspected"]))
    .withColumn("txn_size_bucket",
        F.when(F.col("amount") < 50,    "Micro")
         .when(F.col("amount") < 500,   "Small")
         .when(F.col("amount") < 5000,  "Medium")
         .when(F.col("amount") < 50000, "Large")
         .otherwise("VeryLarge")
    )
    .withColumn("is_cross_currency",
        F.col("t.currency") != F.col("a.currency")
    )
    .withColumn("_gold_created_at", F.current_timestamp())
    # Select final columns
    .select(
        "transaction_id", "account_id", "customer_id",
        "full_name", "country", "segment", "credit_score",
        "account_type", "account_status", "branch_code",
        "transaction_date", "txn_year", "txn_month",
        "transaction_type", "amount", "t.currency",
        "channel", "status", "merchant_category", "merchant_name",
        "description", "is_flagged",
        "fraud_label", "is_fraud", "reviewed_by",
        "txn_size_bucket", "is_cross_currency",
        "_gold_created_at"
    )
)

(
    fact_transactions.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("txn_year", "txn_month")
    .saveAsTable(f"{CATALOG}.{GOLD_DB}.fact_transactions")
)
print(f"✅  fact_transactions → {fact_transactions.count():,} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Gold: Dimension Tables

# COMMAND ----------

# dim_customers
dim_customers = (
    silver_cust
    .filter(F.col("is_current") == True)
    .select(
        "customer_id", "first_name", "last_name",
        "email", "phone", "country", "segment",
        "date_joined", "credit_score", "is_active",
        "effective_start", "effective_end", "is_current",
        "_silver_processed_at"
    )
    .withColumn("customer_tenure_days",
        F.datediff(F.current_date(), F.col("date_joined"))
    )
    .withColumn("credit_band",
        F.when(F.col("credit_score") >= 750, "Excellent")
         .when(F.col("credit_score") >= 650, "Good")
         .when(F.col("credit_score") >= 580, "Fair")
         .otherwise("Poor")
    )
)

(
    dim_customers.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.{GOLD_DB}.dim_customers")
)
print(f"✅  dim_customers → {dim_customers.count():,} rows")

# dim_accounts
dim_accounts = (
    silver_acc
    .withColumn("days_since_open", F.datediff(F.current_date(), F.col("open_date")))
)
(
    dim_accounts.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.{GOLD_DB}.dim_accounts")
)
print(f"✅  dim_accounts → {dim_accounts.count():,} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Gold: Daily Transaction Summary (KPI table)

# COMMAND ----------

agg_daily = (
    fact_transactions
    .groupBy("txn_year", "txn_month", "transaction_date",
             "transaction_type", "channel", "currency")
    .agg(
        F.count("transaction_id")             .alias("total_transactions"),
        F.sum("amount")                       .alias("total_amount"),
        F.avg("amount")                       .alias("avg_amount"),
        F.min("amount")                       .alias("min_amount"),
        F.max("amount")                       .alias("max_amount"),
        F.countDistinct("account_id")         .alias("unique_accounts"),
        F.countDistinct("customer_id")        .alias("unique_customers"),
        F.sum(F.col("is_fraud").cast("int"))  .alias("fraud_count"),
        F.count(F.when(F.col("status") == "Failed", True)).alias("failed_count"),
        F.count(F.when(F.col("status") == "Completed", True)).alias("completed_count"),
    )
    .withColumn("fraud_rate",   F.round(F.col("fraud_count") / F.col("total_transactions"), 4))
    .withColumn("failure_rate", F.round(F.col("failed_count") / F.col("total_transactions"), 4))
    .withColumn("_gold_created_at", F.current_timestamp())
)

(
    agg_daily.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("txn_year", "txn_month")
    .saveAsTable(f"{CATALOG}.{GOLD_DB}.agg_daily_txn_summary")
)
print(f"✅  agg_daily_txn_summary → {agg_daily.count():,} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Gold: Customer 360 View

# COMMAND ----------

customer_360 = (
    fact_transactions
    .groupBy("customer_id", "full_name", "country", "segment", "credit_score")
    .agg(
        F.count("transaction_id")                             .alias("total_transactions"),
        F.sum("amount")                                       .alias("total_spend"),
        F.avg("amount")                                       .alias("avg_txn_amount"),
        F.max("transaction_date")                             .alias("last_txn_date"),
        F.min("transaction_date")                             .alias("first_txn_date"),
        F.countDistinct("account_id")                         .alias("total_accounts"),
        F.sum(F.col("is_fraud").cast("int"))                  .alias("fraud_count"),
        F.countDistinct("merchant_category")                  .alias("merchant_diversity"),
        F.first("credit_score")                               .alias("credit_score_latest"),
        F.collect_set("channel")                              .alias("channels_used"),
        F.count(F.when(F.col("status") == "Failed", True))   .alias("failed_txns"),
    )
    .withColumn("fraud_rate",
        F.round(F.col("fraud_count") / F.col("total_transactions"), 4)
    )
    .withColumn("days_since_last_txn",
        F.datediff(F.current_date(), F.col("last_txn_date"))
    )
    .withColumn("customer_value_tier",
        F.when(F.col("total_spend") > 500_000, "Platinum")
         .when(F.col("total_spend") > 100_000, "Gold")
         .when(F.col("total_spend") >  20_000, "Silver")
         .otherwise("Bronze")
    )
    .withColumn("_gold_created_at", F.current_timestamp())
)

(
    customer_360.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.{GOLD_DB}.agg_customer_360")
)
print(f"✅  agg_customer_360 → {customer_360.count():,} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Gold: Fraud Analysis

# COMMAND ----------

fraud_analysis = (
    fact_transactions
    .filter(F.col("is_fraud") == True)
    .groupBy(
        "txn_year", "txn_month", "transaction_type",
        "channel", "merchant_category", "country",
        "txn_size_bucket", "fraud_label"
    )
    .agg(
        F.count("transaction_id")   .alias("fraud_txn_count"),
        F.sum("amount")             .alias("fraud_total_amount"),
        F.avg("amount")             .alias("fraud_avg_amount"),
        F.countDistinct("customer_id").alias("affected_customers"),
        F.countDistinct("account_id") .alias("affected_accounts"),
    )
    .withColumn("_gold_created_at", F.current_timestamp())
)

(
    fraud_analysis.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("txn_year", "txn_month")
    .saveAsTable(f"{CATALOG}.{GOLD_DB}.agg_fraud_analysis")
)
print(f"✅  agg_fraud_analysis → {fraud_analysis.count():,} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Gold: Channel Performance

# COMMAND ----------

channel_perf = (
    fact_transactions
    .groupBy("txn_year", "txn_month", "channel", "transaction_type")
    .agg(
        F.count("transaction_id")           .alias("txn_count"),
        F.sum("amount")                     .alias("total_amount"),
        F.avg("amount")                     .alias("avg_amount"),
        F.count(F.when(F.col("status") == "Completed", True)).alias("completed"),
        F.count(F.when(F.col("status") == "Failed", True))   .alias("failed"),
        F.sum(F.col("is_fraud").cast("int")).alias("fraud_count"),
    )
    .withColumn("success_rate",
        F.round(F.col("completed") / F.col("txn_count"), 4)
    )
)
(
    channel_perf.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.{GOLD_DB}.agg_channel_performance")
)
print(f"✅  agg_channel_performance → {channel_perf.count():,} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Gold: Merchant Insights

# COMMAND ----------

merchant_insights = (
    fact_transactions
    .groupBy("merchant_category", "merchant_name", "country", "segment")
    .agg(
        F.count("transaction_id")   .alias("txn_count"),
        F.sum("amount")             .alias("total_spend"),
        F.avg("amount")             .alias("avg_spend"),
        F.countDistinct("customer_id").alias("unique_customers"),
    )
    .withColumn("spend_rank",
        F.rank().over(
            Window.partitionBy("merchant_category")
                  .orderBy(F.col("total_spend").desc())
        )
    )
)
(
    merchant_insights.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.{GOLD_DB}.agg_merchant_insights")
)
print(f"✅  agg_merchant_insights → {merchant_insights.count():,} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Optimise Gold tables (Z-ORDER)

# COMMAND ----------

gold_tables_optimize = {
    "fact_transactions"      : "transaction_date, customer_id",
    "agg_daily_txn_summary"  : "transaction_date",
    "agg_customer_360"       : "customer_id",
    "agg_fraud_analysis"     : "txn_year, txn_month",
    "agg_channel_performance": "channel",
}

for table, zorder_cols in gold_tables_optimize.items():
    spark.sql(f"""
        OPTIMIZE {CATALOG}.{GOLD_DB}.{table}
        ZORDER BY ({zorder_cols})
    """)
    print(f"⚡  OPTIMIZE + Z-ORDER  →  {table}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 9. Gold Summary

# COMMAND ----------

gold_tables = [
    "fact_transactions", "dim_customers", "dim_accounts",
    "agg_daily_txn_summary", "agg_customer_360",
    "agg_fraud_analysis", "agg_channel_performance", "agg_merchant_insights"
]

print("\n" + "="*65)
print("  🥇 GOLD LAYER — AGGREGATION SUMMARY")
print("="*65)
for t in gold_tables:
    count = spark.sql(f"SELECT COUNT(*) AS cnt FROM {CATALOG}.{GOLD_DB}.{t}").collect()[0]["cnt"]
    print(f"   {t:<35} {count:>10,} rows")
print("="*65)
print(f"   Run date: {RUN_DATE}  |  Status: ✅ COMPLETE")
print("   📊 Gold tables ready for Power BI consumption!")
