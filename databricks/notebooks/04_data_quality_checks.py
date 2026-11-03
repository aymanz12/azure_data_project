# Databricks notebook source
# ============================================================
# Notebook : 04_data_quality_checks.py
# Layer    : Cross-layer DQ validation
# Purpose  : Comprehensive data quality framework using
#            Great Expectations-style checks implemented
#            natively with PySpark.
#            Results are written to a DQ results Delta table.
# Author   : Data Engineering Team
# ============================================================

# COMMAND ----------
# MAGIC %md
# MAGIC # ✅ Data Quality Checks Framework
# MAGIC
# MAGIC Runs after Silver transformation. Validates:
# MAGIC - **Completeness** — No nulls in critical fields
# MAGIC - **Uniqueness**   — Primary keys are unique
# MAGIC - **Validity**     — Values within expected ranges/sets
# MAGIC - **Referential Integrity** — FKs exist in parent tables
# MAGIC - **Timeliness**   — No stale or future-dated records
# MAGIC - **Volume**       — Row counts within expected thresholds

# COMMAND ----------

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import *
from datetime import datetime
import json

spark = SparkSession.builder.appName("DataQualityChecks").getOrCreate()

CATALOG   = "banking_catalog"
SILVER_DB = "silver"
GOLD_DB   = "gold"
DQ_DB     = "dq_results"
RUN_DATE  = dbutils.widgets.get("run_date") if "run_date" in [w.name for w in dbutils.widgets.getAll()] else str(datetime.today().date())

spark.sql(f"CREATE DATABASE IF NOT EXISTS {CATALOG}.{DQ_DB}")

# ── DQ Result Schema ──────────────────────────────────────────────────────────
DQ_SCHEMA = StructType([
    StructField("check_id",       StringType(),    False),
    StructField("check_name",     StringType(),    False),
    StructField("table_name",     StringType(),    False),
    StructField("column_name",    StringType(),    True),
    StructField("check_type",     StringType(),    False),
    StructField("expected",       StringType(),    True),
    StructField("actual",         StringType(),    True),
    StructField("passed",         BooleanType(),   False),
    StructField("severity",       StringType(),    False),   # CRITICAL / WARNING / INFO
    StructField("failure_count",  LongType(),      True),
    StructField("total_count",    LongType(),      True),
    StructField("pass_rate",      DoubleType(),    True),
    StructField("run_date",       DateType(),      False),
    StructField("checked_at",     TimestampType(), False),
])

dq_results = []

def add_result(check_id, check_name, table, column, check_type,
               expected, actual, passed, severity="CRITICAL",
               failure_count=0, total_count=0):
    pass_rate = round((total_count - failure_count) / total_count, 4) if total_count > 0 else 1.0
    dq_results.append({
        "check_id"     : check_id,
        "check_name"   : check_name,
        "table_name"   : table,
        "column_name"  : column,
        "check_type"   : check_type,
        "expected"     : str(expected),
        "actual"       : str(actual),
        "passed"       : passed,
        "severity"     : severity,
        "failure_count": failure_count,
        "total_count"  : total_count,
        "pass_rate"    : pass_rate,
        "run_date"     : datetime.strptime(RUN_DATE, "%Y-%m-%d").date(),
        "checked_at"   : datetime.utcnow(),
    })
    status = "✅ PASS" if passed else ("🔴 FAIL" if severity == "CRITICAL" else "⚠️  WARN")
    print(f"   {status} | {check_name:<45} | pass_rate={pass_rate:.1%}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Load Silver Tables

# COMMAND ----------

silver_txn    = spark.table(f"{CATALOG}.{SILVER_DB}.transactions")
silver_cust   = spark.table(f"{CATALOG}.{SILVER_DB}.customers")
silver_acc    = spark.table(f"{CATALOG}.{SILVER_DB}.accounts")
silver_fraud  = spark.table(f"{CATALOG}.{SILVER_DB}.fraud_labels")

print("📥 Silver tables loaded")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Completeness Checks

# COMMAND ----------

print("\n── COMPLETENESS CHECKS ────────────────────────────────────")

def check_not_null(df, table, col, severity="CRITICAL"):
    total   = df.count()
    nulls   = df.filter(F.col(col).isNull()).count()
    passed  = nulls == 0
    add_result(
        check_id=f"COMP_{table.upper()}_{col.upper()}",
        check_name=f"[{table}] {col} must not be null",
        table=table, column=col, check_type="COMPLETENESS",
        expected="0 nulls", actual=f"{nulls} nulls",
        passed=passed, severity=severity,
        failure_count=nulls, total_count=total
    )

# Transactions
for col in ["transaction_id", "account_id", "amount", "transaction_date", "status"]:
    check_not_null(silver_txn, "silver.transactions", col, "CRITICAL")

for col in ["currency", "transaction_type", "channel"]:
    check_not_null(silver_txn, "silver.transactions", col, "WARNING")

# Customers
for col in ["customer_id", "first_name", "last_name", "country", "segment"]:
    check_not_null(silver_cust, "silver.customers", col, "CRITICAL")

for col in ["email", "credit_score"]:
    check_not_null(silver_cust, "silver.customers", col, "WARNING")

# Accounts
for col in ["account_id", "customer_id", "account_type", "balance"]:
    check_not_null(silver_acc, "silver.accounts", col, "CRITICAL")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Uniqueness Checks

# COMMAND ----------

print("\n── UNIQUENESS CHECKS ──────────────────────────────────────")

def check_unique(df, table, col, severity="CRITICAL"):
    total   = df.count()
    dupes   = total - df.select(col).distinct().count()
    passed  = dupes == 0
    add_result(
        check_id=f"UNIQ_{table.upper()}_{col.upper()}",
        check_name=f"[{table}] {col} must be unique",
        table=table, column=col, check_type="UNIQUENESS",
        expected="0 duplicates", actual=f"{dupes} duplicates",
        passed=passed, severity=severity,
        failure_count=dupes, total_count=total
    )

check_unique(silver_txn,  "silver.transactions", "transaction_id", "CRITICAL")
check_unique(silver_cust, "silver.customers",    "customer_id",    "CRITICAL")
check_unique(silver_acc,  "silver.accounts",     "account_id",     "CRITICAL")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Validity Checks

# COMMAND ----------

print("\n── VALIDITY CHECKS ────────────────────────────────────────")

# Amount must be positive
total = silver_txn.count()
neg_amounts = silver_txn.filter(F.col("amount") <= 0).count()
add_result(
    check_id="VAL_TXN_AMOUNT_POSITIVE",
    check_name="[transactions] amount must be > 0",
    table="silver.transactions", column="amount", check_type="VALIDITY",
    expected=">0", actual=f"{neg_amounts} non-positive",
    passed=neg_amounts == 0, severity="CRITICAL",
    failure_count=neg_amounts, total_count=total
)

# Currency must be valid ISO codes
valid_currencies = ["USD", "EUR", "GBP", "CAD", "AUD", "CHF", "JPY", "NGN", "ZAR"]
invalid_ccy = silver_txn.filter(~F.col("currency").isin(valid_currencies)).count()
add_result(
    check_id="VAL_TXN_CURRENCY",
    check_name="[transactions] currency must be valid ISO code",
    table="silver.transactions", column="currency", check_type="VALIDITY",
    expected=f"One of {valid_currencies}", actual=f"{invalid_ccy} invalid",
    passed=invalid_ccy == 0, severity="WARNING",
    failure_count=invalid_ccy, total_count=total
)

# Status must be in allowed set
valid_statuses = ["Completed", "Failed", "Pending", "Reversed"]
invalid_status = silver_txn.filter(~F.col("status").isin(valid_statuses)).count()
add_result(
    check_id="VAL_TXN_STATUS",
    check_name="[transactions] status must be in allowed set",
    table="silver.transactions", column="status", check_type="VALIDITY",
    expected=str(valid_statuses), actual=f"{invalid_status} invalid",
    passed=invalid_status == 0, severity="CRITICAL",
    failure_count=invalid_status, total_count=total
)

# Credit score between 300 and 850
cust_total = silver_cust.count()
bad_credit = silver_cust.filter(
    (F.col("credit_score") < 300) | (F.col("credit_score") > 850)
).count()
add_result(
    check_id="VAL_CUST_CREDIT_SCORE",
    check_name="[customers] credit_score must be 300–850",
    table="silver.customers", column="credit_score", check_type="VALIDITY",
    expected="300–850", actual=f"{bad_credit} out of range",
    passed=bad_credit == 0, severity="WARNING",
    failure_count=bad_credit, total_count=cust_total
)

# Account balance not excessively negative
acc_total = silver_acc.count()
bad_balance = silver_acc.filter(F.col("balance") < -10000).count()
add_result(
    check_id="VAL_ACC_BALANCE",
    check_name="[accounts] balance not severely negative (< -10000)",
    table="silver.accounts", column="balance", check_type="VALIDITY",
    expected=">=−10000", actual=f"{bad_balance} rows",
    passed=bad_balance == 0, severity="WARNING",
    failure_count=bad_balance, total_count=acc_total
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Referential Integrity Checks

# COMMAND ----------

print("\n── REFERENTIAL INTEGRITY CHECKS ───────────────────────────")

# All transaction account_ids exist in accounts
valid_acc_ids = set(r.account_id for r in silver_acc.select("account_id").collect())
orphan_txns = silver_txn.filter(~F.col("account_id").isin(valid_acc_ids)).count()
add_result(
    check_id="REF_TXN_ACCOUNT_ID",
    check_name="[transactions] account_id must exist in accounts",
    table="silver.transactions", column="account_id", check_type="REFERENTIAL_INTEGRITY",
    expected="All account_ids in silver.accounts",
    actual=f"{orphan_txns} orphan transactions",
    passed=orphan_txns == 0, severity="CRITICAL",
    failure_count=orphan_txns, total_count=total
)

# All account customer_ids exist in customers
valid_cust_ids = set(r.customer_id for r in silver_cust.select("customer_id").collect())
orphan_accs = silver_acc.filter(~F.col("customer_id").isin(valid_cust_ids)).count()
add_result(
    check_id="REF_ACC_CUSTOMER_ID",
    check_name="[accounts] customer_id must exist in customers",
    table="silver.accounts", column="customer_id", check_type="REFERENTIAL_INTEGRITY",
    expected="All customer_ids in silver.customers",
    actual=f"{orphan_accs} orphan accounts",
    passed=orphan_accs == 0, severity="CRITICAL",
    failure_count=orphan_accs, total_count=acc_total
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Timeliness Checks

# COMMAND ----------

print("\n── TIMELINESS CHECKS ──────────────────────────────────────")

# No transactions with future dates
future_txns = silver_txn.filter(F.col("transaction_date") > F.current_timestamp()).count()
add_result(
    check_id="TIME_TXN_FUTURE_DATE",
    check_name="[transactions] no future-dated transactions",
    table="silver.transactions", column="transaction_date", check_type="TIMELINESS",
    expected="0 future dates", actual=f"{future_txns} future dates",
    passed=future_txns == 0, severity="WARNING",
    failure_count=future_txns, total_count=total
)

# No transactions older than 2 years
stale_txns = silver_txn.filter(
    F.col("transaction_date") < F.date_sub(F.current_date(), 730)
).count()
add_result(
    check_id="TIME_TXN_STALE",
    check_name="[transactions] no transactions older than 2 years",
    table="silver.transactions", column="transaction_date", check_type="TIMELINESS",
    expected="0 stale records", actual=f"{stale_txns} stale",
    passed=stale_txns == 0, severity="INFO",
    failure_count=stale_txns, total_count=total
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Volume Checks

# COMMAND ----------

print("\n── VOLUME CHECKS ──────────────────────────────────────────")

def check_volume(df, table, min_rows, max_rows=None, severity="WARNING"):
    count = df.count()
    if max_rows:
        passed = min_rows <= count <= max_rows
        expected = f"{min_rows:,}–{max_rows:,}"
    else:
        passed = count >= min_rows
        expected = f">={min_rows:,}"
    add_result(
        check_id=f"VOL_{table.upper().replace('.','_')}",
        check_name=f"[{table}] row count in expected range",
        table=table, column=None, check_type="VOLUME",
        expected=expected, actual=f"{count:,}",
        passed=passed, severity=severity,
        failure_count=0 if passed else 1, total_count=1
    )

check_volume(silver_txn,   "silver.transactions", min_rows=1_000,  severity="CRITICAL")
check_volume(silver_cust,  "silver.customers",    min_rows=100,    severity="CRITICAL")
check_volume(silver_acc,   "silver.accounts",     min_rows=100,    severity="CRITICAL")
check_volume(silver_fraud, "silver.fraud_labels", min_rows=0,      severity="INFO")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Write DQ Results to Delta

# COMMAND ----------

dq_df = spark.createDataFrame(dq_results, schema=DQ_SCHEMA)

(
    dq_df.write.format("delta")
    .mode("append")
    .option("mergeSchema", "true")
    .partitionBy("run_date")
    .saveAsTable(f"{CATALOG}.{DQ_DB}.dq_check_results")
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 9. DQ Summary Dashboard

# COMMAND ----------

total_checks    = len(dq_results)
passed_checks   = sum(1 for r in dq_results if r["passed"])
critical_fails  = sum(1 for r in dq_results if not r["passed"] and r["severity"] == "CRITICAL")
warning_fails   = sum(1 for r in dq_results if not r["passed"] and r["severity"] == "WARNING")

print("\n" + "="*65)
print("  ✅ DATA QUALITY CHECK SUMMARY")
print("="*65)
print(f"   Total Checks    : {total_checks}")
print(f"   ✅ Passed        : {passed_checks}")
print(f"   🔴 Critical Fail: {critical_fails}")
print(f"   ⚠️  Warning Fail : {warning_fails}")
print(f"   Overall Pass %  : {passed_checks/total_checks:.1%}")
print("="*65)

# Fail pipeline if any CRITICAL check fails
if critical_fails > 0:
    failed_list = [r["check_name"] for r in dq_results if not r["passed"] and r["severity"] == "CRITICAL"]
    raise Exception(
        f"❌ {critical_fails} CRITICAL data quality check(s) failed:\n" +
        "\n".join(f"  - {c}" for c in failed_list)
    )

print(f"\n   ✅ All critical DQ checks passed on {RUN_DATE}!")
