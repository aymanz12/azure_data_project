import json
import requests
from pathlib import Path

DASHBOARDS_DIR = Path(r"c:\Users\hp\Desktop\data-engineering-projects\azure-project\grafana\dashboards")
DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)

DS = {"type": "frser-sqlite-datasource", "uid": "BankingAnalytics"}

def make_target(sql, query_type="table", time_columns=None):
    t = {
        "datasource": DS,
        "queryText": sql,
        "rawQueryText": sql,
        "rawQuery": True,
        "queryType": query_type,
        "refId": "A"
    }
    if time_columns:
        t["timeColumns"] = time_columns
    return t

# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD 1: Transaction & Channel Overview
# ─────────────────────────────────────────────────────────────────────────────

d1 = {
    "annotations": {"list": []},
    "editable": True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 1,
    "id": None,
    "links": [
        {
            "asDropdown": False,
            "icon": "dashboard",
            "includeVars": True,
            "keepTime": True,
            "tags": [],
            "targetBlank": False,
            "title": "👉 Open Fraud & Customer Intelligence",
            "type": "link",
            "url": "/d/banking_fraud_customer_intel"
        }
    ],
    "liveNow": False,
    "panels": [
        # --- ROW 1: Executive KPIs ---
        {
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
            "id": 100,
            "title": "Executive KPI Overview",
            "type": "row",
            "panels": []
        },
        {
            "id": 1,
            "title": "Total Transactions",
            "type": "stat",
            "gridPos": {"h": 4, "w": 6, "x": 0, "y": 1},
            "datasource": DS,
            "targets": [make_target("SELECT COUNT(*) as value FROM fact_transactions;")],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "semi-dark-blue"},
                    "unit": "short",
                    "thresholds": {"mode": "absolute", "steps": [{"color": "semi-dark-blue", "value": None}]}
                }
            },
            "options": {
                "colorMode": "background",
                "graphMode": "none",
                "justifyMode": "center",
                "orientation": "auto",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                "textMode": "auto"
            }
        },
        {
            "id": 2,
            "title": "Total Transaction Volume (USD)",
            "type": "stat",
            "gridPos": {"h": 4, "w": 6, "x": 6, "y": 1},
            "datasource": DS,
            "targets": [make_target("SELECT ROUND(SUM(amount), 2) as value FROM fact_transactions;")],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "semi-dark-green"},
                    "unit": "currencyUSD",
                    "thresholds": {"mode": "absolute", "steps": [{"color": "semi-dark-green", "value": None}]}
                }
            },
            "options": {
                "colorMode": "background",
                "graphMode": "none",
                "justifyMode": "center",
                "orientation": "auto",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                "textMode": "auto"
            }
        },
        {
            "id": 3,
            "title": "Average Transaction Value",
            "type": "stat",
            "gridPos": {"h": 4, "w": 6, "x": 12, "y": 1},
            "datasource": DS,
            "targets": [make_target("SELECT ROUND(AVG(amount), 2) as value FROM fact_transactions;")],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "semi-dark-purple"},
                    "unit": "currencyUSD",
                    "thresholds": {"mode": "absolute", "steps": [{"color": "semi-dark-purple", "value": None}]}
                }
            },
            "options": {
                "colorMode": "background",
                "graphMode": "none",
                "justifyMode": "center",
                "orientation": "auto",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                "textMode": "auto"
            }
        },
        {
            "id": 4,
            "title": "Active Global Markets",
            "type": "stat",
            "gridPos": {"h": 4, "w": 6, "x": 18, "y": 1},
            "datasource": DS,
            "targets": [make_target("SELECT COUNT(DISTINCT country) as value FROM fact_transactions;")],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "semi-dark-orange"},
                    "unit": "short",
                    "thresholds": {"mode": "absolute", "steps": [{"color": "semi-dark-orange", "value": None}]}
                }
            },
            "options": {
                "colorMode": "background",
                "graphMode": "none",
                "justifyMode": "center",
                "orientation": "auto",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                "textMode": "auto"
            }
        },

        # --- ROW 2: Transaction Trends & Channel Revenue ---
        {
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": 5},
            "id": 101,
            "title": "Volume & Channel Performance",
            "type": "row",
            "panels": []
        },
        {
            "id": 5,
            "title": "Daily Transaction Volume Trend (USD)",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 14, "x": 0, "y": 6},
            "datasource": DS,
            "targets": [make_target(
                "SELECT strftime('%s', transaction_date_only) * 1000 AS time, ROUND(SUM(total_amount), 2) AS 'Daily Volume (USD)' FROM agg_daily_txn_summary GROUP BY transaction_date_only ORDER BY transaction_date_only ASC;",
                query_type="time series",
                time_columns=["time"]
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "custom": {
                        "drawStyle": "line",
                        "lineInterpolation": "smooth",
                        "lineWidth": 2,
                        "fillOpacity": 20,
                        "gradientMode": "opacity"
                    },
                    "unit": "currencyUSD"
                }
            },
            "options": {
                "legend": {"displayMode": "table", "placement": "bottom", "calcs": ["sum", "mean", "max"]},
                "tooltip": {"mode": "single", "sort": "none"}
            }
        },
        {
            "id": 6,
            "title": "Total Revenue by Channel (USD)",
            "type": "barchart",
            "gridPos": {"h": 8, "w": 10, "x": 14, "y": 6},
            "datasource": DS,
            "targets": [make_target(
                "SELECT channel, ROUND(SUM(total_amount), 2) AS 'Revenue (USD)' FROM agg_channel_performance GROUP BY channel ORDER BY 'Revenue (USD)' DESC;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "unit": "currencyUSD"
                }
            },
            "options": {
                "orientation": "auto",
                "showValue": "always"
            }
        },

        # --- ROW 3: Merchant Category & Channel Volume ---
        {
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14},
            "id": 102,
            "title": "Category Distribution & Channel Counts",
            "type": "row",
            "panels": []
        },
        {
            "id": 7,
            "title": "Transaction Distribution by Merchant Category",
            "type": "piechart",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 15},
            "datasource": DS,
            "targets": [make_target(
                "SELECT merchant_category, COUNT(*) AS count FROM fact_transactions GROUP BY merchant_category ORDER BY count DESC LIMIT 10;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "unit": "short"
                }
            },
            "options": {
                "displayLabels": ["percent", "name"],
                "legend": {"displayMode": "table", "placement": "right", "values": ["value", "percent"]},
                "pieType": "donut",
                "reduceOptions": {"values": True}
            }
        },
        {
            "id": 8,
            "title": "Transaction Count by Banking Channel",
            "type": "barchart",
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 15},
            "datasource": DS,
            "targets": [make_target(
                "SELECT channel, SUM(txn_count) AS Transactions FROM agg_channel_performance GROUP BY channel ORDER BY Transactions DESC;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "unit": "short"
                }
            },
            "options": {
                "orientation": "auto",
                "showValue": "always"
            }
        },

        # --- ROW 4: Geographic Analysis & Channel Success Rate ---
        {
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": 23},
            "id": 103,
            "title": "Geographic Breakdown & Channel Operational Quality",
            "type": "row",
            "panels": []
        },
        {
            "id": 9,
            "title": "Top Markets by Total Spend (USD)",
            "type": "barchart",
            "gridPos": {"h": 8, "w": 11, "x": 0, "y": 24},
            "datasource": DS,
            "targets": [make_target(
                "SELECT country, ROUND(SUM(amount), 2) AS 'Total Volume' FROM fact_transactions GROUP BY country ORDER BY 'Total Volume' DESC LIMIT 10;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "unit": "currencyUSD"
                }
            },
            "options": {
                "orientation": "horizontal",
                "showValue": "always"
            }
        },
        {
            "id": 10,
            "title": "Channel Performance & Success Rate Summary",
            "type": "table",
            "gridPos": {"h": 8, "w": 13, "x": 11, "y": 24},
            "datasource": DS,
            "targets": [make_target(
                "SELECT channel AS Channel, SUM(txn_count) AS 'Total Txns', ROUND(SUM(total_amount), 2) AS 'Total Volume ($)', SUM(completed) AS Completed, SUM(failed) AS Failed, SUM(fraud_count) AS 'Fraud Txns', ROUND(AVG(success_rate) * 100, 2) AS 'Success Rate %' FROM agg_channel_performance GROUP BY channel ORDER BY 'Total Volume ($)' DESC;"
            )],
            "fieldConfig": {
                "defaults": {
                    "custom": {
                        "align": "auto",
                        "displayMode": "auto"
                    }
                },
                "overrides": [
                    {
                        "matcher": {"id": "byName", "options": "Success Rate %"},
                        "properties": [
                            {"id": "unit", "value": "percent"},
                            {"id": "custom.displayMode", "value": "color-background"},
                            {
                                "id": "thresholds",
                                "value": {
                                    "mode": "absolute",
                                    "steps": [
                                        {"color": "red", "value": None},
                                        {"color": "yellow", "value": 85},
                                        {"color": "green", "value": 90}
                                    ]
                                }
                            }
                        ]
                    },
                    {
                        "matcher": {"id": "byName", "options": "Total Volume ($)"},
                        "properties": [{"id": "unit", "value": "currencyUSD"}]
                    }
                ]
            },
            "options": {
                "footer": {"enablePagination": False, "show": True},
                "showHeader": True,
                "sortBy": [{"desc": True, "displayName": "Total Volume ($)"}]
            }
        }
    ],
    "refresh": "",
    "schemaVersion": 39,
    "tags": ["banking", "transactions", "executive"],
    "templating": {"list": []},
    "time": {"from": "now-5y", "to": "now"},
    "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m"], "time_options": ["5m", "15m", "1h", "6h", "12h", "24h", "2d", "7d", "30d", "90d", "1y", "5y"]},
    "timezone": "browser",
    "title": "🏦 Banking - Transaction & Channel Overview",
    "uid": "banking_txn_channel_overview",
    "version": 10
}

with open(DASHBOARDS_DIR / "dashboard1_transactions.json", "w", encoding="utf-8") as f:
    json.dump(d1, f, indent=2)
print("Updated dashboard1_transactions.json")


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD 2: Fraud & Customer Intelligence
# ─────────────────────────────────────────────────────────────────────────────

d2 = {
    "annotations": {"list": []},
    "editable": True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 1,
    "id": None,
    "links": [
        {
            "asDropdown": False,
            "icon": "dashboard",
            "includeVars": True,
            "keepTime": True,
            "tags": [],
            "targetBlank": False,
            "title": "👉 Open Transaction & Channel Overview",
            "type": "link",
            "url": "/d/banking_txn_channel_overview"
        }
    ],
    "liveNow": False,
    "panels": [
        # --- ROW 1: Fraud Executive KPIs ---
        {
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
            "id": 200,
            "title": "Fraud Risk & Loss Metrics",
            "type": "row",
            "panels": []
        },
        {
            "id": 21,
            "title": "Overall Fraud Rate",
            "type": "stat",
            "gridPos": {"h": 4, "w": 6, "x": 0, "y": 1},
            "datasource": DS,
            "targets": [make_target(
                "SELECT ROUND(100.0 * SUM(fraud_txn_count) / (SELECT COUNT(*) FROM fact_transactions), 2) AS value FROM agg_fraud_analysis;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "thresholds"},
                    "unit": "percent",
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "orange", "value": 1.0},
                            {"color": "red", "value": 2.0}
                        ]
                    }
                }
            },
            "options": {
                "colorMode": "background",
                "graphMode": "none",
                "justifyMode": "center",
                "orientation": "auto",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                "textMode": "auto"
            }
        },
        {
            "id": 22,
            "title": "Total Fraud Losses (USD)",
            "type": "stat",
            "gridPos": {"h": 4, "w": 6, "x": 6, "y": 1},
            "datasource": DS,
            "targets": [make_target(
                "SELECT ROUND(SUM(fraud_total_amount), 2) as value FROM agg_fraud_analysis;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "semi-dark-red"},
                    "unit": "currencyUSD",
                    "thresholds": {"mode": "absolute", "steps": [{"color": "semi-dark-red", "value": None}]}
                }
            },
            "options": {
                "colorMode": "background",
                "graphMode": "none",
                "justifyMode": "center",
                "orientation": "auto",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                "textMode": "auto"
            }
        },
        {
            "id": 23,
            "title": "Total Fraud Incidents",
            "type": "stat",
            "gridPos": {"h": 4, "w": 6, "x": 12, "y": 1},
            "datasource": DS,
            "targets": [make_target(
                "SELECT SUM(fraud_txn_count) as value FROM agg_fraud_analysis;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "semi-dark-orange"},
                    "unit": "short",
                    "thresholds": {"mode": "absolute", "steps": [{"color": "semi-dark-orange", "value": None}]}
                }
            },
            "options": {
                "colorMode": "background",
                "graphMode": "none",
                "justifyMode": "center",
                "orientation": "auto",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                "textMode": "auto"
            }
        },
        {
            "id": 24,
            "title": "Affected Customers",
            "type": "stat",
            "gridPos": {"h": 4, "w": 6, "x": 18, "y": 1},
            "datasource": DS,
            "targets": [make_target(
                "SELECT SUM(affected_customers) as value FROM agg_fraud_analysis;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "dark-red"},
                    "unit": "short",
                    "thresholds": {"mode": "absolute", "steps": [{"color": "dark-red", "value": None}]}
                }
            },
            "options": {
                "colorMode": "background",
                "graphMode": "none",
                "justifyMode": "center",
                "orientation": "auto",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                "textMode": "auto"
            }
        },

        # --- ROW 2: Fraud Attack Vectors & Breakdown ---
        {
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": 5},
            "id": 201,
            "title": "Fraud by Geography & Channel",
            "type": "row",
            "panels": []
        },
        {
            "id": 25,
            "title": "Fraud Losses by Country (USD)",
            "type": "barchart",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 6},
            "datasource": DS,
            "targets": [make_target(
                "SELECT country, ROUND(SUM(fraud_total_amount), 2) AS 'Fraud Amount' FROM agg_fraud_analysis GROUP BY country ORDER BY 'Fraud Amount' DESC LIMIT 10;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "semi-dark-red"},
                    "unit": "currencyUSD"
                }
            },
            "options": {
                "orientation": "auto",
                "showValue": "always"
            }
        },
        {
            "id": 26,
            "title": "Fraud Incidents by Channel",
            "type": "barchart",
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 6},
            "datasource": DS,
            "targets": [make_target(
                "SELECT channel, SUM(fraud_txn_count) AS 'Fraud Incidents' FROM agg_fraud_analysis GROUP BY channel ORDER BY 'Fraud Incidents' DESC;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "semi-dark-orange"},
                    "unit": "short"
                }
            },
            "options": {
                "orientation": "auto",
                "showValue": "always"
            }
        },

        # --- ROW 3: Merchant Category & Customer 360 Segmentation ---
        {
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14},
            "id": 202,
            "title": "Merchant Exposure & Customer 360",
            "type": "row",
            "panels": []
        },
        {
            "id": 27,
            "title": "Fraud Distribution by Merchant Category",
            "type": "piechart",
            "gridPos": {"h": 8, "w": 8, "x": 0, "y": 15},
            "datasource": DS,
            "targets": [make_target(
                "SELECT merchant_category, SUM(fraud_txn_count) AS 'Fraud Count' FROM agg_fraud_analysis GROUP BY merchant_category ORDER BY 'Fraud Count' DESC LIMIT 10;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "unit": "short"
                }
            },
            "options": {
                "displayLabels": ["percent", "name"],
                "legend": {"displayMode": "table", "placement": "bottom", "values": ["value", "percent"]},
                "pieType": "donut",
                "reduceOptions": {"values": True}
            }
        },
        {
            "id": 28,
            "title": "Customers by Account Segment",
            "type": "piechart",
            "gridPos": {"h": 8, "w": 8, "x": 8, "y": 15},
            "datasource": DS,
            "targets": [make_target(
                "SELECT segment, COUNT(*) AS count FROM agg_customer_360 GROUP BY segment ORDER BY count DESC;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "unit": "short"
                }
            },
            "options": {
                "displayLabels": ["percent", "name"],
                "legend": {"displayMode": "table", "placement": "bottom", "values": ["value", "percent"]},
                "pieType": "pie",
                "reduceOptions": {"values": True}
            }
        },
        {
            "id": 29,
            "title": "Customers by Value Tier",
            "type": "bargauge",
            "gridPos": {"h": 8, "w": 8, "x": 16, "y": 15},
            "datasource": DS,
            "targets": [make_target(
                "SELECT customer_value_tier, COUNT(*) AS Customers FROM agg_customer_360 GROUP BY customer_value_tier ORDER BY Customers DESC;"
            )],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "unit": "short"
                }
            },
            "options": {
                "displayMode": "gradient",
                "orientation": "horizontal",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                "showUnfilled": True
            }
        },

        # --- ROW 4: Detailed Investigation Table ---
        {
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": 23},
            "id": 203,
            "title": "Forensic Investigation & Top Fraud Cases",
            "type": "row",
            "panels": []
        },
        {
            "id": 30,
            "title": "High-Risk Fraud Vectors Summary",
            "type": "table",
            "gridPos": {"h": 9, "w": 24, "x": 0, "y": 24},
            "datasource": DS,
            "targets": [make_target(
                "SELECT country AS Country, channel AS Channel, merchant_category AS 'Merchant Category', fraud_label AS 'Status', SUM(fraud_txn_count) AS 'Fraud Txns', ROUND(SUM(fraud_total_amount), 2) AS 'Total Fraud Losses ($)', ROUND(AVG(fraud_avg_amount), 2) AS 'Avg Loss/Txn ($)', SUM(affected_customers) AS 'Victims' FROM agg_fraud_analysis GROUP BY country, channel, merchant_category, fraud_label ORDER BY 'Total Fraud Losses ($)' DESC LIMIT 20;"
            )],
            "fieldConfig": {
                "defaults": {
                    "custom": {
                        "align": "auto",
                        "displayMode": "auto"
                    }
                },
                "overrides": [
                    {
                        "matcher": {"id": "byName", "options": "Total Fraud Losses ($)"},
                        "properties": [
                            {"id": "unit", "value": "currencyUSD"},
                            {"id": "custom.displayMode", "value": "color-background"},
                            {
                                "id": "thresholds",
                                "value": {
                                    "mode": "absolute",
                                    "steps": [
                                        {"color": "dark-orange", "value": None},
                                        {"color": "red", "value": 10000}
                                    ]
                                }
                            }
                        ]
                    },
                    {
                        "matcher": {"id": "byName", "options": "Avg Loss/Txn ($)"},
                        "properties": [{"id": "unit", "value": "currencyUSD"}]
                    }
                ]
            },
            "options": {
                "footer": {"enablePagination": True, "show": True},
                "showHeader": True,
                "sortBy": [{"desc": True, "displayName": "Total Fraud Losses ($)"}]
            }
        }
    ],
    "refresh": "",
    "schemaVersion": 39,
    "tags": ["banking", "fraud", "customer-360"],
    "templating": {"list": []},
    "time": {"from": "now-5y", "to": "now"},
    "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m"], "time_options": ["5m", "15m", "1h", "6h", "12h", "24h", "2d", "7d", "30d", "90d", "1y", "5y"]},
    "timezone": "browser",
    "title": "🛡️ Banking - Fraud & Customer Intelligence",
    "uid": "banking_fraud_customer_intel",
    "version": 10
}

with open(DASHBOARDS_DIR / "dashboard2_fraud.json", "w", encoding="utf-8") as f:
    json.dump(d2, f, indent=2)
print("Updated dashboard2_fraud.json")

# Push directly to Grafana API
BASE = "http://localhost:3000"
auth = ("admin", "admin123")
for dash in [d1, d2]:
    r = requests.post(f"{BASE}/api/dashboards/db", json={"dashboard": dash, "overwrite": True}, auth=auth)
    print(f"Pushed {dash['uid']} to Grafana: {r.status_code}")
