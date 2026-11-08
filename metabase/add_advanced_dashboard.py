"""
Metabase: Fix Branch channel chart + Add Dashboard 3 (Advanced Analytics & Maps).
Run after setup_metabase.py has already been executed.
"""
import requests, json, sys

BASE_URL       = "http://localhost:3000"
ADMIN_EMAIL    = "admin@banking.local"
ADMIN_PASSWORD = "Admin123!"
DB_ID          = 2

session = requests.Session()

def api(method, path, **kwargs):
    url = f"{BASE_URL}/api{path}"
    r = getattr(session, method)(url, **kwargs)
    if not r.ok:
        print(f"  [x] {method.upper()} {path} => {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
    return r.json()

def authenticate():
    resp = api("post", "/session", json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    session.headers["X-Metabase-Session"] = resp["id"]
    print("[OK] Authenticated.")

def find_card(name):
    r = api("get", "/card")
    items = r if isinstance(r, list) else r.get("data", [])
    for c in items:
        if c.get("name") == name:
            return c["id"]
    return None

def update_card(card_id, native_sql, display=None, visualization_settings=None):
    payload = {"dataset_query": {
        "type": "native",
        "database": DB_ID,
        "native": {"query": native_sql, "template-tags": {}},
    }}
    if display:
        payload["display"] = display
    if visualization_settings is not None:
        payload["visualization_settings"] = visualization_settings
    api("put", f"/card/{card_id}", json=payload)
    print(f"  [OK] Updated card id={card_id}")

def create_question(name, collection_id, native_sql, display="table", viz=None):
    # idempotent
    r = api("get", "/card")
    items = r if isinstance(r, list) else r.get("data", [])
    for c in items:
        if c.get("name") == name:
            print(f"  [info] Card '{name}' already exists (id={c['id']})")
            return c["id"]
    resp = api("post", "/card", json={
        "name": name,
        "collection_id": collection_id,
        "dataset_query": {
            "type": "native", "database": DB_ID,
            "native": {"query": native_sql, "template-tags": {}},
        },
        "display": display,
        "visualization_settings": viz or {},
    })
    return resp["id"]

def create_collection(name, description=""):
    existing = api("get", "/collection")
    items = existing if isinstance(existing, list) else existing.get("data", [])
    for c in items:
        if c.get("name") == name:
            return c["id"]
    resp = api("post", "/collection", json={"name": name, "description": description, "color": "#7172AD"})
    return resp["id"]

def create_dashboard(name, description, collection_id):
    existing = api("get", "/dashboard")
    items = existing if isinstance(existing, list) else existing.get("data", [])
    for d in items:
        if d.get("name") == name:
            return d["id"]
    resp = api("post", "/dashboard", json={"name": name, "description": description, "collection_id": collection_id})
    return resp["id"]

def add_cards_to_dashboard(dashboard_id, card_specs):
    dashcards = [
        {
            "id": -(i + 1),
            "card_id":  s["card_id"],
            "row":      s["row"],
            "col":      s["col"],
            "size_x":   s["size_x"],
            "size_y":   s["size_y"],
            "parameter_mappings": [],
            "visualization_settings": s.get("viz_override", {}),
            "series": [],
        }
        for i, s in enumerate(card_specs)
    ]
    api("put", f"/dashboard/{dashboard_id}", json={"dashcards": dashcards})


# =============================================================================
# MAIN
# =============================================================================
authenticate()

# ─────────────────────────────────────────────────────────────────────────────
# 1. FIX: Total Revenue by Channel — normalize casing, use UPPER(), direct fact
# ─────────────────────────────────────────────────────────────────────────────
print("\n[FIX] Updating 'Total Revenue by Channel (USD)' question ...")
card_id = find_card("Total Revenue by Channel (USD)")
if card_id:
    update_card(
        card_id,
        # Normalize channel names to UPPER so Metabase groups them cleanly
        """SELECT UPPER(channel)              AS "Channel",
                  ROUND(SUM(amount), 2)      AS "Revenue (USD)"
           FROM   fact_transactions
           GROUP  BY UPPER(channel)
           ORDER  BY 2 DESC;""",
        display="bar",
        visualization_settings={
            "graph.dimensions": ["Channel"],
            "graph.metrics":    ["Revenue (USD)"],
            "graph.colors":     ["#509EE3"],
            "graph.x_axis.labels_enabled": True,
            "graph.show_values": True,
        },
    )
else:
    print("  [warn] Card not found — skipping fix.")

# ─────────────────────────────────────────────────────────────────────────────
# 2. NEW DASHBOARD 3 — Advanced Analytics & Geographic Intelligence
# ─────────────────────────────────────────────────────────────────────────────
print("\n[DIR] Creating Advanced Analytics collection ...")
adv_col_id = create_collection("Advanced Analytics", "Dashboard 3 advanced questions")

print("\n[CHART] Creating advanced questions ...")

# --- Row 0: KPI numbers -------------------------------------------------------
q_fraud_pct_confirmed = create_question(
    "Confirmed vs Suspected Fraud Split",
    adv_col_id,
    """SELECT fraud_label        AS "Fraud Type",
              SUM(fraud_txn_count) AS "Incidents",
              ROUND(SUM(fraud_total_amount), 2) AS "Total Loss (USD)"
       FROM   agg_fraud_analysis
       GROUP  BY fraud_label
       ORDER  BY 2 DESC;""",
    display="pie",
    viz={"pie.dimension": "Fraud Type", "pie.metric": "Incidents"},
)

q_avg_fraud_loss = create_question(
    "Avg Fraud Loss per Incident (USD)",
    adv_col_id,
    "SELECT ROUND(SUM(fraud_total_amount)/NULLIF(SUM(fraud_txn_count),0), 2) AS \"Avg Loss/Incident (USD)\" FROM agg_fraud_analysis;",
    display="scalar",
    viz={},
)

q_top_fraud_country = create_question(
    "Highest Fraud Rate Country",
    adv_col_id,
    """SELECT fa.country                                           AS "Country",
              ROUND(100.0 * SUM(fa.fraud_txn_count) / ft.total_txns, 4) AS "Fraud Rate (%)",
              SUM(fa.fraud_txn_count)                            AS "Fraud Txns",
              ft.total_txns                                      AS "Total Txns"
       FROM   agg_fraud_analysis fa
       JOIN   (
           SELECT country, COUNT(*) AS total_txns
           FROM   fact_transactions
           GROUP  BY country
       ) ft ON fa.country = ft.country
       GROUP  BY fa.country, ft.total_txns
       ORDER  BY 2 DESC
       LIMIT  1;""",
    display="scalar",
    viz={"scalar.field": "Country"},
)

q_customer_count = create_question(
    "Total Unique Customers",
    adv_col_id,
    "SELECT COUNT(DISTINCT customer_id) AS \"Unique Customers\" FROM fact_transactions;",
    display="scalar",
    viz={},
)

# --- Map: Transaction volume by country (ISO 2-letter codes) ------------------
q_txn_map = create_question(
    "Transaction Volume by Country (Map)",
    adv_col_id,
    """SELECT country            AS "Country",
              COUNT(*)           AS "Transactions",
              ROUND(SUM(amount), 2) AS "Total Volume (USD)"
       FROM   fact_transactions
       GROUP  BY country
       ORDER  BY 3 DESC;""",
    display="map",
    viz={
        "map.type": "region",
        "map.region": "world_countries",
        "map.metric_column": "Total Volume (USD)",
        "map.dimension_column": "Country",
        "map.colors": ["#C4E4FF", "#509EE3", "#0A3875"],
    },
)

# --- Map: Fraud losses by country --------------------------------------------
q_fraud_map = create_question(
    "Fraud Loss Heatmap by Country (Map)",
    adv_col_id,
    """SELECT country                            AS "Country",
              ROUND(SUM(fraud_total_amount), 2)  AS "Fraud Loss (USD)",
              SUM(fraud_txn_count)               AS "Fraud Cases"
       FROM   agg_fraud_analysis
       GROUP  BY country
       ORDER  BY 2 DESC;""",
    display="map",
    viz={
        "map.type": "region",
        "map.region": "world_countries",
        "map.metric_column": "Fraud Loss (USD)",
        "map.dimension_column": "Country",
        "map.colors": ["#FFF3CD", "#F9A825", "#B71C1C"],
    },
)

# --- Monthly fraud trend (line) -----------------------------------------------
q_monthly_fraud = create_question(
    "Monthly Fraud Loss Trend (USD)",
    adv_col_id,
    """SELECT txn_year || '-' || PRINTF('%02d', txn_month) AS "Month",
              ROUND(SUM(fraud_total_amount), 2)             AS "Fraud Loss (USD)",
              SUM(fraud_txn_count)                          AS "Fraud Cases"
       FROM   agg_fraud_analysis
       GROUP  BY txn_year, txn_month
       ORDER  BY txn_year, txn_month;""",
    display="line",
    viz={
        "graph.dimensions": ["Month"],
        "graph.metrics":    ["Fraud Loss (USD)", "Fraud Cases"],
        "graph.colors":     ["#ED6E6E", "#F9CF48"],
    },
)

# --- Channel fraud rate comparison (bar) --------------------------------------
q_channel_fraud_rate = create_question(
    "Fraud Rate by Channel (%)",
    adv_col_id,
    """SELECT UPPER(channel)       AS "Channel",
              ROUND(100.0 * SUM(fraud_count) / NULLIF(SUM(txn_count), 0), 2) AS "Fraud Rate (%)"
       FROM   agg_channel_performance
       GROUP  BY UPPER(channel)
       ORDER  BY 2 DESC;""",
    display="bar",
    viz={
        "graph.dimensions": ["Channel"],
        "graph.metrics":    ["Fraud Rate (%)"],
        "graph.colors":     ["#ED6E6E"],
        "graph.show_values": True,
    },
)

# --- Success vs Failure rate scatter / row chart ------------------------------
q_channel_success_bar = create_question(
    "Channel Success vs Failure Rate (%)",
    adv_col_id,
    """SELECT UPPER(channel)       AS "Channel",
              ROUND(AVG(success_rate) * 100, 2)                       AS "Success Rate (%)",
              ROUND(100.0 * SUM(failed) / NULLIF(SUM(txn_count), 0), 2) AS "Failure Rate (%)"
       FROM   agg_channel_performance
       GROUP  BY UPPER(channel)
       ORDER  BY 2 DESC;""",
    display="bar",
    viz={
        "graph.dimensions": ["Channel"],
        "graph.metrics":    ["Success Rate (%)", "Failure Rate (%)"],
        "graph.colors":     ["#84BB4C", "#ED6E6E"],
        "graph.x_axis.labels_enabled": True,
        "stackable.stack_type": "normalized",
        "graph.show_values": True,
    },
)

# --- Customer spend distribution (scatter via table + row chart) ---------------
q_spend_tier_avg = create_question(
    "Avg Spend & Fraud Rate by Customer Tier",
    adv_col_id,
    """SELECT customer_value_tier          AS "Tier",
              COUNT(*)                     AS "Customers",
              ROUND(AVG(total_spend), 2)   AS "Avg Spend (USD)",
              ROUND(AVG(fraud_rate) * 100, 4) AS "Avg Fraud Rate (%)",
              ROUND(AVG(total_transactions), 1) AS "Avg Transactions"
       FROM   agg_customer_360
       GROUP  BY customer_value_tier
       ORDER  BY 3 DESC;""",
    display="bar",
    viz={
        "graph.dimensions": ["Tier"],
        "graph.metrics":    ["Avg Spend (USD)", "Avg Fraud Rate (%)"],
        "graph.colors":     ["#A989C5", "#F9CF48"],
        "graph.show_values": True,
    },
)

# --- Merchant category revenue vs fraud (combo) -------------------------------
q_merch_rev_fraud = create_question(
    "Merchant Category: Revenue vs Fraud Loss",
    adv_col_id,
    """SELECT ft.merchant_category              AS "Category",
              ROUND(SUM(ft.amount), 2)          AS "Total Revenue (USD)",
              ROUND(COALESCE(SUM(fa.fraud_total_amount), 0), 2) AS "Fraud Loss (USD)"
       FROM   fact_transactions ft
       LEFT JOIN agg_fraud_analysis fa
              ON ft.merchant_category = fa.merchant_category
       GROUP  BY ft.merchant_category
       ORDER  BY 2 DESC
       LIMIT  10;""",
    display="bar",
    viz={
        "graph.dimensions": ["Category"],
        "graph.metrics":    ["Total Revenue (USD)", "Fraud Loss (USD)"],
        "graph.colors":     ["#509EE3", "#ED6E6E"],
        "graph.show_values": False,
    },
)

# --- Transaction type breakdown -----------------------------------------------
q_txn_type = create_question(
    "Transaction Type Breakdown",
    adv_col_id,
    """SELECT transaction_type    AS "Type",
              COUNT(*)            AS "Count",
              ROUND(SUM(amount), 2) AS "Volume (USD)"
       FROM   fact_transactions
       GROUP  BY transaction_type
       ORDER  BY 3 DESC;""",
    display="row",
    viz={
        "graph.dimensions": ["Type"],
        "graph.metrics":    ["Volume (USD)"],
        "graph.colors":     ["#7172AD"],
        "graph.show_values": True,
    },
)

# --- Customer segment spend heatmap (table with coloring) ---------------------
q_segment_country = create_question(
    "Customer Spend by Segment & Country (Top 10)",
    adv_col_id,
    """SELECT c.country            AS "Country",
              c.segment            AS "Segment",
              COUNT(*)             AS "Customers",
              ROUND(SUM(c.total_spend), 2) AS "Total Spend (USD)",
              ROUND(AVG(c.avg_txn_amount), 2) AS "Avg Txn (USD)"
       FROM   agg_customer_360 c
       GROUP  BY c.country, c.segment
       ORDER  BY 4 DESC
       LIMIT  20;""",
    display="table",
    viz={},
)

print("  [OK] All advanced questions created.")

# =============================================================================
# BUILD DASHBOARD 3
# =============================================================================
print("\nBuilding Dashboard 3 — Advanced Analytics & Geographic Intelligence ...")
dash3_id = create_dashboard(
    "Advanced Analytics & Geographic Intelligence",
    "World maps, monthly trends, channel diagnostics, merchant revenue vs fraud, customer tier analysis.",
    adv_col_id,
)

add_cards_to_dashboard(dash3_id, [
    # Row 0: 4 KPI scalars
    {"card_id": q_avg_fraud_loss,       "row": 0,  "col": 0,  "size_x": 6,  "size_y": 3},
    {"card_id": q_top_fraud_country,    "row": 0,  "col": 6,  "size_x": 6,  "size_y": 3},
    {"card_id": q_customer_count,       "row": 0,  "col": 12, "size_x": 6,  "size_y": 3},
    {"card_id": q_fraud_pct_confirmed,  "row": 0,  "col": 18, "size_x": 6,  "size_y": 6},

    # Row 3: Transaction volume world map (18 cols) | confirmed pie already on right
    {"card_id": q_txn_map,             "row": 3,  "col": 0,  "size_x": 18, "size_y": 8},

    # Row 11: Fraud loss world map (18) | fraud rate by channel (6)
    {"card_id": q_fraud_map,           "row": 11, "col": 0,  "size_x": 18, "size_y": 8},
    {"card_id": q_channel_fraud_rate,  "row": 11, "col": 18, "size_x": 6,  "size_y": 8},

    # Row 19: Monthly fraud trend (full width)
    {"card_id": q_monthly_fraud,       "row": 19, "col": 0,  "size_x": 24, "size_y": 7},

    # Row 26: Channel success vs failure (12) | Merchant revenue vs fraud (12)
    {"card_id": q_channel_success_bar, "row": 26, "col": 0,  "size_x": 12, "size_y": 7},
    {"card_id": q_merch_rev_fraud,     "row": 26, "col": 12, "size_x": 12, "size_y": 7},

    # Row 33: Customer tier avg spend (12) | Txn type row chart (12)
    {"card_id": q_spend_tier_avg,      "row": 33, "col": 0,  "size_x": 12, "size_y": 7},
    {"card_id": q_txn_type,            "row": 33, "col": 12, "size_x": 12, "size_y": 7},

    # Row 40: Full-width customer segment x country table
    {"card_id": q_segment_country,     "row": 40, "col": 0,  "size_x": 24, "size_y": 8},
])

print(f"  [OK] Dashboard 3 built (id={dash3_id}).\n")
print("=" * 60)
print("All done!")
print(f"  Dashboard 3 : {BASE_URL}/dashboard/{dash3_id}")
print("=" * 60)
