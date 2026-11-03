# 🏦 Banking Analytics - Modern Grafana Dashboards

Modern, high-performance dashboards with zero broken dependencies and **native Databricks connection support**.

---

## 🚀 Quick Access

- **Grafana URL:** [http://localhost:3000](http://localhost:3000)
- **Username:** `admin`
- **Password:** `admin123`

### 📊 Included Dashboards

1. **🏦 Transaction & Channel Overview:**
   - **Direct link:** [http://localhost:3000/d/banking_txn_channel_overview](http://localhost:3000/d/banking_txn_channel_overview)
   - **Executive KPIs:** Total Transactions (49.6K), Total Volume ($12.45M), Average Transaction ($250.85), Active Global Markets.
   - **Daily Volume Trends:** Smooth time-series line chart of daily spend.
   - **Channel Performance:** Revenue by channel (POS, Mobile, Branch, Web, ATM) & transaction distribution.
   - **Merchant Category Share:** Donut chart breakdown.
   - **Operational Quality Table:** Channels sorted by volume with colored success rate badges.

2. **🛡️ Fraud & Customer Intelligence:**
   - **Direct link:** [http://localhost:3000/d/banking_fraud_customer_intel](http://localhost:3000/d/banking_fraud_customer_intel)
   - **Risk KPIs:** Overall Fraud Rate (with threshold alert colors), Total Losses ($235K), Incident Count, Affected Customers.
   - **Attack Vectors:** Losses by Country (US, UK, FR, CA, DE) and Fraud by Channel.
   - **Customer 360:** Segmentation (Corporate, Retail, SME) & Customer Value Tiers (Bronze, Silver, Gold, Platinum).
   - **Forensic Table:** Top fraud vectors with color-coded loss severity.

---

## ☁️ Connecting to Azure Databricks

Grafana can connect directly to your **Azure Databricks SQL Warehouse** or **Databricks Cluster** to query Delta tables (`fact_transactions`, `gold_*`, etc.) live.

### Option A: Using the Infinity Plugin (Installed & Configured)

The `yesoreyeram-infinity-datasource` plugin is pre-installed in your container. It queries Databricks via the **Databricks SQL Statement Execution API**:

1. In Grafana, navigate to **Connections** → **Data Sources** → **Add data source** → Search **Infinity**.
2. Set:
   - **Authentication:** `Bearer Token`
   - **Token:** Your Databricks Personal Access Token (`dapi...`)
   - **Base URL:** `https://adb-<workspace-id>.azuredatabricks.net/api/2.0/sql/statements`
3. In any panel, use HTTP POST with SQL payload:
   ```json
   {
     "warehouse_id": "<your-databricks-sql-warehouse-id>",
     "statement": "SELECT channel, SUM(total_amount) as volume FROM gold.agg_channel_performance GROUP BY channel"
   }
   ```

### Option B: Using Databricks SQL via ODBC/JDBC or Postgres Wire

You can connect Databricks to Grafana using the standard SQL connector:
1. In Databricks, open your **SQL Warehouse** → **Connection Details**.
2. Note:
   - **Server Hostname:** `adb-<workspace-id>.azuredatabricks.net`
   - **HTTP Path:** `/sql/1.0/warehouses/<warehouse-id>`
   - **Port:** `443`
   - **Token:** Personal Access Token

---

## 🛠️ Docker Management

To restart or manage Grafana:

```powershell
# From the azure-project/grafana directory:
docker compose ps
docker compose restart
docker compose down
docker compose up -d
```
