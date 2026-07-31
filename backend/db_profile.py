from app.services.mysql_service import MySQLService
from app.config import settings
import json

db = MySQLService(
    host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
    user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
    database=settings.MYSQL_DATABASE
)

queries = {
    "ROW COUNTS": """
        SELECT 'Leakage_Activity' as tbl, COUNT(*) as cnt FROM Leakage_Activity
        UNION ALL SELECT 'Reverse_Claims', COUNT(*) FROM Reverse_Claims
        UNION ALL SELECT 'copay_Claims_Transactions', COUNT(*) FROM copay_Claims_Transactions
        UNION ALL SELECT 'Product_Master', COUNT(*) FROM Product_Master
        UNION ALL SELECT 'hcp_master', COUNT(*) FROM hcp_master
        UNION ALL SELECT 'fatigue_score', COUNT(*) FROM fatigue_score
        UNION ALL SELECT 'hcp_engagement_logs', COUNT(*) FROM hcp_engagement_logs
        UNION ALL SELECT 'campaign_master', COUNT(*) FROM campaign_master
        UNION ALL SELECT 'Payer_Master', COUNT(*) FROM Payer_Master
        UNION ALL SELECT 'Compliance_Table', COUNT(*) FROM Compliance_Table
        UNION ALL SELECT 'leakage_history', COUNT(*) FROM leakage_history
        UNION ALL SELECT 'territory_master', COUNT(*) FROM territory_master
        UNION ALL SELECT 'Reject_Code_Master', COUNT(*) FROM Reject_Code_Master
        UNION ALL SELECT 'Zip_Geography_Master', COUNT(*) FROM Zip_Geography_Master
    """,
    "LEAKAGE STATES": "SELECT DISTINCT State FROM Leakage_Activity ORDER BY State",
    "LEAKAGE BRANDS (sample)": "SELECT DISTINCT BrandName FROM Leakage_Activity ORDER BY BrandName LIMIT 15",
    "LEAKAGE DATE RANGE": "SELECT MIN(Processed_TimeStamp) as earliest, MAX(Processed_TimeStamp) as latest FROM Leakage_Activity",
    "HCP SPECIALTIES": "SELECT DISTINCT specialty FROM hcp_master ORDER BY specialty",
    "HCP PRACTICE STATES": "SELECT DISTINCT practice_state FROM hcp_master ORDER BY practice_state",
    "FATIGUE RANGE": "SELECT MIN(Fatigue) as min_f, MAX(Fatigue) as max_f, AVG(Fatigue) as avg_f FROM fatigue_score",
    "FATIGUE PRODUCTS": "SELECT DISTINCT Product FROM fatigue_score ORDER BY Product",
    "ENGAGEMENT CHANNELS": "SELECT DISTINCT Channel FROM hcp_engagement_logs",
    "ENGAGEMENT DATE RANGE": "SELECT MIN(Engagement_Date) as earliest, MAX(Engagement_Date) as latest FROM hcp_engagement_logs",
    "CAMPAIGN CHANNELS": "SELECT DISTINCT channel FROM campaign_master ORDER BY channel",
    "CAMPAIGN STATUSES": "SELECT DISTINCT status FROM campaign_master",
    "CAMPAIGN TYPES": "SELECT DISTINCT campaign_type FROM campaign_master",
    "CAMPAIGN DATE RANGE": "SELECT MIN(start_date) as earliest_start, MAX(end_date) as latest_end FROM campaign_master",
    "PAYER TYPES": "SELECT DISTINCT payer_type FROM Payer_Master",
    "COMPLIANCE DATE RANGE": "SELECT MIN(Created_At) as earliest, MAX(Created_At) as latest FROM Compliance_Table",
    "COMPLIANCE PAYER TYPES": "SELECT DISTINCT Payer_Type FROM Compliance_Table",
    "LEAKAGE HISTORY RANGE": "SELECT MIN(updated_at) as earliest, MAX(updated_at) as latest FROM leakage_history",
    "TERRITORY STATES": "SELECT DISTINCT state FROM territory_master ORDER BY state LIMIT 15",
    "TERRITORY SEGMENTS": "SELECT DISTINCT segment FROM territory_master",
    "COPAY DATE RANGE": "SELECT MIN(transaction_datetime) as earliest, MAX(transaction_datetime) as latest FROM copay_Claims_Transactions",
    "COPAY CLAIM STATUSES": "SELECT DISTINCT claim_status FROM copay_Claims_Transactions",
    "COPAY RESPONSE STATUSES": "SELECT DISTINCT Response_Status FROM copay_Claims_Transactions",
    "COPAY REJECT CODES (top 10)": "SELECT reject_code, COUNT(*) as cnt FROM copay_Claims_Transactions WHERE reject_code IS NOT NULL AND reject_code != '' GROUP BY reject_code ORDER BY cnt DESC LIMIT 10",
    "COPAY BRANDS (sample)": "SELECT DISTINCT BrandName FROM copay_Claims_Transactions WHERE BrandName IS NOT NULL LIMIT 10",
    "REJECT SEVERITIES": "SELECT DISTINCT severity FROM Reject_Code_Master",
    "REVERSE_CLAIMS SAMPLE": "SELECT * FROM Reverse_Claims LIMIT 5",
}

for label, sql in queries.items():
    try:
        result = json.loads(db.execute_sql(sql))
        records = result.get('records', [])
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        for r in records:
            print(f"  {r}")
    except Exception as e:
        print(f"\n  {label}: ERROR - {e}")
