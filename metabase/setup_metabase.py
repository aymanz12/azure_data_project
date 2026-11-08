"""
Metabase Setup Script — Banking Analytics Platform
===================================================
Automates the full Metabase onboarding sequence via the REST API:

  1.  Wait for Metabase to become healthy
  2.  Complete the initial setup wizard (admin account + site prefs)
  3.  Add the SQLite database (banking.db)
  4.  Wait for the database schema sync to finish
  5.  Create all saved Questions for Dashboard 1 (Transactions & Channels)
  6.  Create all saved Questions for Dashboard 2 (Fraud & Customer 360)
  7.  Assemble both dashboards and place every card on a grid

Usage:
    python metabase/setup_metabase.py

Requirements:
    pip install requests
"""

import time
import sys
import requests

# --- Connection settings ------------------------------------------------------
BASE_URL  = "http://localhost:3000"
ADMIN_EMAIL    = "admin@banking.local"
ADMIN_PASSWORD = "Admin123!"
ADMIN_FIRST    = "Banking"
ADMIN_LAST     = "Admin"
SITE_NAME      = "Banking Analytics"
DB_PATH        = "/data/banking.db"   # path inside the container

session = requests.Session()


# --- Helpers ------------------------------------------------------------------

def api(method: str, path: str, **kwargs):
    url = f"{BASE_URL}/api{path}"
    r = getattr(session, method)(url, **kwargs)
    if not r.ok:
        print(f"  ✗ {method.upper()} {path}  →  {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
    return r.json()


def wait_for_metabase(timeout: int = 300):
    print("[wait] Waiting for Metabase to start …")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/api/health", timeout=5)
            if r.ok and r.json().get("status") == "ok":
                print("[OK] Metabase is healthy.\n")
                return
        except Exception:
            pass
        time.sleep(5)
    print("[ERR] Metabase did not become healthy in time. Is Docker running?")
    sys.exit(1)


def setup_wizard():
    """Complete the first-time setup wizard."""
    print("[setup] Running initial setup wizard …")
    token_resp = api("get", "/session/properties")
    setup_token = token_resp.get("setup-token")
    if not setup_token:
        print("  [info]  Setup token not found — wizard may already be complete.")
        return

    payload = {
        "token": setup_token,
        "user": {
            "email":      ADMIN_EMAIL,
            "password":   ADMIN_PASSWORD,
            "first_name": ADMIN_FIRST,
            "last_name":  ADMIN_LAST,
            "site_name":  SITE_NAME,
        },
        "prefs": {
            "site_name":    SITE_NAME,
            "site_locale":  "en",
            "allow_tracking": False,
        },
        "database": None,
    }
    api("post", "/setup", json=payload)
    print("  [OK] Wizard complete.\n")


def authenticate():
    """Obtain a session token and attach it to every request."""
    print("[auth] Authenticating …")
    resp = api("post", "/session", json={
        "username": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
    })
    session.headers["X-Metabase-Session"] = resp["id"]
    print("  [OK] Authenticated.\n")


def add_database() -> int:
    """Register the SQLite banking.db; return its database ID."""
    print("[db]  Registering SQLite database …")
    # Check if already exists
    dbs = api("get", "/database")
    items = dbs if isinstance(dbs, list) else dbs.get("data", [])
    for db in items:
        if db.get("engine") == "sqlite" and DB_PATH in str(db.get("details", {})):
            db_id = db["id"]
            print(f"  [info]  Database already registered (id={db_id}).\n")
            return db_id

    db_resp = api("post", "/database", json={
        "engine": "sqlite",
        "name":   "Banking Analytics (SQLite)",
        "details": {"db": DB_PATH},
        "auto_run_queries": True,
        "is_full_sync": True,
        "schedules": {},
    })
    db_id = db_resp["id"]
    print(f"  [OK] Database registered (id={db_id}).\n")
    return db_id


def wait_for_sync(db_id: int, timeout: int = 180):
    """Poll until Metabase has synced all tables from the database."""
    print("[wait] Waiting for schema sync …")
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = api("get", f"/database/{db_id}/metadata")
        tables = resp.get("tables", [])
        names  = {t["name"] for t in tables}
        required = {"fact_transactions", "agg_channel_performance",
                    "agg_daily_txn_summary", "agg_fraud_analysis",
                    "agg_customer_360"}
        if required.issubset(names):
            print(f"  [OK] Synced {len(tables)} tables.\n")
            return
        print(f"  … found {names & required} of {len(required)} required tables, retrying …")
        time.sleep(10)
    print("  [warn]  Sync timed out — continuing anyway.")


def get_table_id(db_id: int, table_name: str) -> int:
    resp = api("get", f"/database/{db_id}/metadata")
    for t in resp.get("tables", []):
        if t["name"] == table_name:
            return t["id"]
    raise ValueError(f"Table '{table_name}' not found in database {db_id}.")


def create_question(name: str, collection_id: int, db_id: int,
                    native_sql: str, display: str = "table",
                    visualization_settings: dict | None = None) -> int:
    """Create a saved question (card) using native SQL and return its card ID. Idempotent."""
    existing = api("get", "/card")
    items = existing if isinstance(existing, list) else existing.get("data", [])
    for c in items:
        if c.get("name") == name:
            return c["id"]
    payload = {
        "name":       name,
        "collection_id": collection_id,
        "dataset_query": {
            "type":     "native",
            "database": db_id,
            "native":   {
                "query": native_sql,
                "template-tags": {},
            },
        },
        "display": display,
        "visualization_settings": visualization_settings or {},
    }
    resp = api("post", "/card", json=payload)
    return resp["id"]


def create_collection(name: str, description: str = "") -> int:
    """Create a collection (folder) for cards; return its ID. Idempotent."""
    existing = api("get", "/collection")
    items = existing if isinstance(existing, list) else existing.get("data", [])
    for c in items:
        if c.get("name") == name:
            return c["id"]
    resp = api("post", "/collection", json={
        "name":        name,
        "description": description,
        "color":       "#509EE3",
    })
    return resp["id"]


def create_dashboard(name: str, description: str, collection_id: int) -> int:
    """Create a dashboard; return its ID. Idempotent by name."""
    existing = api("get", "/dashboard")
    items = existing if isinstance(existing, list) else existing.get("data", [])
    for d in items:
        if d.get("name") == name:
            return d["id"]
    resp = api("post", "/dashboard", json={
        "name":          name,
        "description":   description,
        "collection_id": collection_id,
    })
    return resp["id"]


def add_cards_to_dashboard(dashboard_id: int, card_specs: list[dict]) -> None:
    """
    Add multiple cards to a dashboard in a single PUT /api/dashboard/:id call.
    card_specs is a list of dicts with keys: card_id, row, col, size_x, size_y.
    Uses Metabase v0.49+ API (PUT dashboard body with dashcards list).
    """
    dashcards = [
        {
            "id": -(i + 1),          # negative id = new dashcard
            "card_id":  spec["card_id"],
            "row":      spec["row"],
            "col":      spec["col"],
            "size_x":   spec["size_x"],
            "size_y":   spec["size_y"],
            "parameter_mappings":     [],
            "visualization_settings": {},
            "series": [],
        }
        for i, spec in enumerate(card_specs)
    ]
    api("put", f"/dashboard/{dashboard_id}", json={"dashcards": dashcards})


# --- Visualization setting helpers --------------------------------------------

def scalar_vs():
    return {"scalar.show_percent": False}


def bar_vs(x_col: str, y_col: str, color: str = "#509EE3"):
    return {
        "graph.dimensions": [x_col],
        "graph.metrics":    [y_col],
        "graph.colors":     [color],
    }


def pie_vs(dim: str, metric: str):
    return {
        "pie.dimension": dim,
        "pie.metric":    metric,
    }


def line_vs(x_col: str, y_col: str):
    return {
        "graph.dimensions": [x_col],
        "graph.metrics":    [y_col],
        "graph.x_axis.scale": "timeseries",
    }


def table_vs():
    return {}


# --- Main ---------------------------------------------------------------------

def main():
    wait_for_metabase()
    setup_wizard()
    authenticate()
    db_id = add_database()
    wait_for_sync(db_id)

    # -- Collections -----------------------------------------------------------
    print("[dir] Creating collections …")
    root_col_id  = create_collection("Banking Analytics", "Banking BI dashboards")
    txn_col_id   = create_collection("Transactions & Channels", "Dashboard 1 questions")
    fraud_col_id = create_collection("Fraud & Customer Intelligence", "Dashboard 2 questions")
    print("  [OK] Collections created.\n")

    # ==========================================================================
    # DASHBOARD 1 — Transaction & Channel Overview
    # ==========================================================================
    print("[chart] Creating Dashboard 1 questions …")

    q_total_txns = create_question(
        "Total Transactions", txn_col_id, db_id,
        "SELECT COUNT(*) AS \"Total Transactions\" FROM fact_transactions;",
        display="scalar", visualization_settings=scalar_vs(),
    )
    q_total_vol = create_question(
        "Total Transaction Volume (USD)", txn_col_id, db_id,
        "SELECT ROUND(SUM(amount), 2) AS \"Total Volume (USD)\" FROM fact_transactions;",
        display="scalar", visualization_settings=scalar_vs(),
    )
    q_avg_txn = create_question(
        "Average Transaction Value (USD)", txn_col_id, db_id,
        "SELECT ROUND(AVG(amount), 2) AS \"Avg Transaction (USD)\" FROM fact_transactions;",
        display="scalar", visualization_settings=scalar_vs(),
    )
    q_markets = create_question(
        "Active Global Markets", txn_col_id, db_id,
        "SELECT COUNT(DISTINCT country) AS \"Active Markets\" FROM fact_transactions;",
        display="scalar", visualization_settings=scalar_vs(),
    )
    q_daily_vol = create_question(
        "Daily Transaction Volume Trend (USD)", txn_col_id, db_id,
        """SELECT transaction_date_only AS "Date",
                  ROUND(SUM(total_amount), 2) AS "Daily Volume (USD)"
           FROM   agg_daily_txn_summary
           GROUP  BY transaction_date_only
           ORDER  BY transaction_date_only ASC;""",
        display="line",
        visualization_settings=line_vs("Date", "Daily Volume (USD)"),
    )
    q_channel_rev = create_question(
        "Total Revenue by Channel (USD)", txn_col_id, db_id,
        """SELECT channel AS "Channel",
                  ROUND(SUM(total_amount), 2) AS "Revenue (USD)"
           FROM   agg_channel_performance
           GROUP  BY channel
           ORDER  BY 2 DESC;""",
        display="bar",
        visualization_settings=bar_vs("Channel", "Revenue (USD)", "#509EE3"),
    )
    q_merch_dist = create_question(
        "Transaction Distribution by Merchant Category", txn_col_id, db_id,
        """SELECT merchant_category AS "Category",
                  COUNT(*) AS "Transactions"
           FROM   fact_transactions
           GROUP  BY merchant_category
           ORDER  BY 2 DESC
           LIMIT  10;""",
        display="pie",
        visualization_settings=pie_vs("Category", "Transactions"),
    )
    q_channel_cnt = create_question(
        "Transaction Count by Banking Channel", txn_col_id, db_id,
        """SELECT channel AS "Channel",
                  SUM(txn_count) AS "Transactions"
           FROM   agg_channel_performance
           GROUP  BY channel
           ORDER  BY 2 DESC;""",
        display="bar",
        visualization_settings=bar_vs("Channel", "Transactions", "#88BF4D"),
    )
    q_top_markets = create_question(
        "Top Markets by Total Spend (USD)", txn_col_id, db_id,
        """SELECT country AS "Country",
                  ROUND(SUM(amount), 2) AS "Total Volume (USD)"
           FROM   fact_transactions
           GROUP  BY country
           ORDER  BY 2 DESC
           LIMIT  10;""",
        display="bar",
        visualization_settings=bar_vs("Country", "Total Volume (USD)", "#A989C5"),
    )
    q_channel_perf = create_question(
        "Channel Performance & Success Rate Summary", txn_col_id, db_id,
        """SELECT channel               AS "Channel",
                  SUM(txn_count)        AS "Total Txns",
                  ROUND(SUM(total_amount), 2) AS "Total Volume ($)",
                  SUM(completed)        AS "Completed",
                  SUM(failed)           AS "Failed",
                  SUM(fraud_count)      AS "Fraud Txns",
                  ROUND(AVG(success_rate) * 100, 2) AS "Success Rate %"
           FROM   agg_channel_performance
           GROUP  BY channel
           ORDER  BY 3 DESC;""",
        display="table", visualization_settings=table_vs(),
    )
    print("  [OK] Dashboard 1 questions created.\n")

    # ==========================================================================
    # DASHBOARD 2 — Fraud & Customer Intelligence
    # ==========================================================================
    print("[chart] Creating Dashboard 2 questions …")

    q_fraud_rate = create_question(
        "Overall Fraud Rate (%)", fraud_col_id, db_id,
        """SELECT ROUND(
                   100.0 * SUM(fraud_txn_count)
                         / (SELECT COUNT(*) FROM fact_transactions),
                   2) AS "Fraud Rate (%)"
           FROM agg_fraud_analysis;""",
        display="scalar", visualization_settings=scalar_vs(),
    )
    q_fraud_loss = create_question(
        "Total Fraud Losses (USD)", fraud_col_id, db_id,
        "SELECT ROUND(SUM(fraud_total_amount), 2) AS \"Total Fraud Losses (USD)\" FROM agg_fraud_analysis;",
        display="scalar", visualization_settings=scalar_vs(),
    )
    q_fraud_incidents = create_question(
        "Total Fraud Incidents", fraud_col_id, db_id,
        "SELECT SUM(fraud_txn_count) AS \"Fraud Incidents\" FROM agg_fraud_analysis;",
        display="scalar", visualization_settings=scalar_vs(),
    )
    q_affected_cust = create_question(
        "Affected Customers", fraud_col_id, db_id,
        "SELECT SUM(affected_customers) AS \"Affected Customers\" FROM agg_fraud_analysis;",
        display="scalar", visualization_settings=scalar_vs(),
    )
    q_fraud_country = create_question(
        "Fraud Losses by Country (USD)", fraud_col_id, db_id,
        """SELECT country AS "Country",
                  ROUND(SUM(fraud_total_amount), 2) AS "Fraud Amount (USD)"
           FROM   agg_fraud_analysis
           GROUP  BY country
           ORDER  BY 2 DESC
           LIMIT  10;""",
        display="bar",
        visualization_settings=bar_vs("Country", "Fraud Amount (USD)", "#ED6E6E"),
    )
    q_fraud_channel = create_question(
        "Fraud Incidents by Channel", fraud_col_id, db_id,
        """SELECT channel AS "Channel",
                  SUM(fraud_txn_count) AS "Fraud Incidents"
           FROM   agg_fraud_analysis
           GROUP  BY channel
           ORDER  BY 2 DESC;""",
        display="bar",
        visualization_settings=bar_vs("Channel", "Fraud Incidents", "#F9CF48"),
    )
    q_fraud_merch = create_question(
        "Fraud Distribution by Merchant Category", fraud_col_id, db_id,
        """SELECT merchant_category AS "Category",
                  SUM(fraud_txn_count) AS "Fraud Count"
           FROM   agg_fraud_analysis
           GROUP  BY merchant_category
           ORDER  BY 2 DESC
           LIMIT  10;""",
        display="pie",
        visualization_settings=pie_vs("Category", "Fraud Count"),
    )
    q_cust_segment = create_question(
        "Customers by Account Segment", fraud_col_id, db_id,
        """SELECT segment AS "Segment",
                  COUNT(*) AS "Customers"
           FROM   agg_customer_360
           GROUP  BY segment
           ORDER  BY 2 DESC;""",
        display="pie",
        visualization_settings=pie_vs("Segment", "Customers"),
    )
    q_cust_tier = create_question(
        "Customers by Value Tier", fraud_col_id, db_id,
        """SELECT customer_value_tier AS "Tier",
                  COUNT(*) AS "Customers"
           FROM   agg_customer_360
           GROUP  BY customer_value_tier
           ORDER  BY 2 DESC;""",
        display="bar",
        visualization_settings=bar_vs("Tier", "Customers", "#84BB4C"),
    )
    q_fraud_forensics = create_question(
        "High-Risk Fraud Vectors Summary", fraud_col_id, db_id,
        """SELECT country                              AS "Country",
                  channel                             AS "Channel",
                  merchant_category                   AS "Merchant Category",
                  fraud_label                         AS "Status",
                  SUM(fraud_txn_count)                AS "Fraud Txns",
                  ROUND(SUM(fraud_total_amount), 2)   AS "Total Fraud Losses ($)",
                  ROUND(AVG(fraud_avg_amount), 2)     AS "Avg Loss/Txn ($)",
                  SUM(affected_customers)             AS "Victims"
           FROM   agg_fraud_analysis
           GROUP  BY country, channel, merchant_category, fraud_label
           ORDER  BY 6 DESC
           LIMIT  20;""",
        display="table", visualization_settings=table_vs(),
    )
    print("  [OK] Dashboard 2 questions created.\n")

    # ==========================================================================
    # BUILD DASHBOARD 1
    # ==========================================================================
    print("Building Dashboard 1 — Transaction & Channel Overview ...")
    dash1_id = create_dashboard(
        " Banking — Transaction & Channel Overview",
        "Executive KPIs, daily volume trends, channel revenue, merchant distribution, and geographic market analysis.",
        root_col_id,
    )
    add_cards_to_dashboard(dash1_id, [
        # Row 0 — 4 KPI scalars
        {"card_id": q_total_txns,   "row": 0,  "col": 0,  "size_x": 6,  "size_y": 3},
        {"card_id": q_total_vol,    "row": 0,  "col": 6,  "size_x": 6,  "size_y": 3},
        {"card_id": q_avg_txn,      "row": 0,  "col": 12, "size_x": 6,  "size_y": 3},
        {"card_id": q_markets,      "row": 0,  "col": 18, "size_x": 6,  "size_y": 3},
        # Row 3 — line chart + bar chart
        {"card_id": q_daily_vol,    "row": 3,  "col": 0,  "size_x": 14, "size_y": 7},
        {"card_id": q_channel_rev,  "row": 3,  "col": 14, "size_x": 10, "size_y": 7},
        # Row 10 — pie + bar
        {"card_id": q_merch_dist,   "row": 10, "col": 0,  "size_x": 12, "size_y": 7},
        {"card_id": q_channel_cnt,  "row": 10, "col": 12, "size_x": 12, "size_y": 7},
        # Row 17 — bar + table
        {"card_id": q_top_markets,  "row": 17, "col": 0,  "size_x": 11, "size_y": 7},
        {"card_id": q_channel_perf, "row": 17, "col": 11, "size_x": 13, "size_y": 7},
    ])
    print(f"  Dashboard 1 built (id={dash1_id}).\n")

    # ==========================================================================
    # BUILD DASHBOARD 2
    # ==========================================================================
    print("Building Dashboard 2 — Fraud & Customer Intelligence ...")
    dash2_id = create_dashboard(
        " Banking — Fraud & Customer Intelligence",
        "Fraud rate KPIs, geographic and channel attack vectors, customer 360 segmentation, and forensic investigation table.",
        root_col_id,
    )
    add_cards_to_dashboard(dash2_id, [
        # Row 0 — 4 KPI scalars
        {"card_id": q_fraud_rate,      "row": 0,  "col": 0,  "size_x": 6,  "size_y": 3},
        {"card_id": q_fraud_loss,      "row": 0,  "col": 6,  "size_x": 6,  "size_y": 3},
        {"card_id": q_fraud_incidents, "row": 0,  "col": 12, "size_x": 6,  "size_y": 3},
        {"card_id": q_affected_cust,   "row": 0,  "col": 18, "size_x": 6,  "size_y": 3},
        # Row 3 — 2 bar charts
        {"card_id": q_fraud_country,   "row": 3,  "col": 0,  "size_x": 12, "size_y": 7},
        {"card_id": q_fraud_channel,   "row": 3,  "col": 12, "size_x": 12, "size_y": 7},
        # Row 10 — pie + pie + bar
        {"card_id": q_fraud_merch,     "row": 10, "col": 0,  "size_x": 8,  "size_y": 7},
        {"card_id": q_cust_segment,    "row": 10, "col": 8,  "size_x": 8,  "size_y": 7},
        {"card_id": q_cust_tier,       "row": 10, "col": 16, "size_x": 8,  "size_y": 7},
        # Row 17 — full-width forensics table
        {"card_id": q_fraud_forensics, "row": 17, "col": 0,  "size_x": 24, "size_y": 8},
    ])
    print(f"  Dashboard 2 built (id={dash2_id}).\n")

    # -- Summary ---------------------------------------------------------------
    print("=" * 60)
    print("Metabase setup complete!")
    print()
    print(f"  Metabase URL : {BASE_URL}")
    print(f"  Login        : {ADMIN_EMAIL}")
    print(f"  Password     : {ADMIN_PASSWORD}")
    print()
    print(f"  Dashboard 1  : {BASE_URL}/dashboard/{dash1_id}")
    print(f"  Dashboard 2  : {BASE_URL}/dashboard/{dash2_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()
