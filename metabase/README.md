# 🏦 Banking Analytics — Metabase BI Platform

Modern, self-service BI dashboards powered by **Metabase v0.52**, connected to the curated Gold-layer SQLite database.

---

## 🚀 Quick Start

### 1. Launch Metabase

```powershell
cd metabase
docker compose up -d
```

Metabase takes ~90 seconds to initialize. Watch readiness:

```powershell
docker compose logs -f metabase
```

### 2. Run the Setup Script

Once Metabase is healthy, run the automated setup script from the project root:

```powershell
python metabase/setup_metabase.py
```

This will:
- Complete the initial wizard (admin account creation)
- Register the SQLite `banking.db` database
- Wait for the schema sync to complete
- Create all saved **Questions** (SQL-native cards)
- Assemble two full **Dashboards** with correct grid layouts

### 3. Open Metabase

| Item | Detail |
|---|---|
| **URL** | http://localhost:3000 |
| **Email** | `admin@banking.local` |
| **Password** | `Admin123!` |

---

## 📊 Dashboards

### 1. 🏦 Transaction & Channel Overview

| Section | Charts |
|---|---|
| Executive KPIs | Total Transactions · Total Volume (USD) · Avg Ticket · Active Markets |
| Volume & Channels | Daily Volume Trend (line) · Revenue by Channel (bar) |
| Category & Channel | Merchant Category Distribution (pie) · Txn Count by Channel (bar) |
| Geographic & Quality | Top Markets by Spend (bar) · Channel Performance Table |

### 2. 🛡️ Fraud & Customer Intelligence

| Section | Charts |
|---|---|
| Risk KPIs | Fraud Rate % · Total Losses (USD) · Fraud Incidents · Affected Customers |
| Attack Vectors | Fraud Losses by Country (bar) · Fraud by Channel (bar) |
| Customer 360 | Fraud by Merchant (pie) · Customers by Segment (pie) · Value Tier (bar) |
| Forensics | High-Risk Fraud Vectors Table (top 20 attack combos) |

---

## ☁️ Connecting to Azure Databricks

Metabase supports Databricks through the **Databricks SQL connector** (Metabase 0.49+):

1. In Metabase, go to **Admin** → **Databases** → **Add database**
2. Choose **Databricks**
3. Fill in:

| Field | Value |
|---|---|
| **Host** | `adb-<workspace-id>.azuredatabricks.net` |
| **HTTP Path** | `/sql/1.0/warehouses/<warehouse-id>` |
| **Personal Access Token** | `dapi...` |
| **Catalog** | `hive_metastore` or Unity Catalog name |
| **Schema** | `gold` |

4. Click **Save** — Metabase will sync all Delta tables automatically.

> [!TIP]
> Once connected to Databricks, your existing saved Questions can be duplicated and their data source switched to the live Databricks database without rebuilding the dashboards.

---

## 🛠️ Docker Management

```powershell
# From the azure-project/metabase directory:
docker compose ps
docker compose restart
docker compose down
docker compose up -d
```

> [!NOTE]
> Dashboard state is persisted in the `metabase_data` Docker volume. Your questions and dashboards survive container restarts.

---

## 📂 Directory Structure

```
metabase/
├── docker-compose.yml      # Metabase + H2 embedded DB service
├── setup_metabase.py       # Full automated API setup script
└── README.md               # This file
```
