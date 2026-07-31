from app.services.mysql_service import MySQLService
from app.config import settings
import json

db = MySQLService(
    host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
    user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
    database=settings.MYSQL_DATABASE
)

queries = {
    "Complex Q1 - 4-Table Copay Rejection Overview": """
        SELECT 
            cct.Transaction_ID,
            cct.BrandName,
            cct.claim_amount,
            CONCAT(hm.hcp_firstName, ' ', hm.hcp_lastName) as physician_name,
            hm.specialty,
            hm.practice_state,
            pm.payer_name,
            pm.payer_type,
            rcm.reject_description,
            rcm.severity
        FROM copay_Claims_Transactions cct
        JOIN hcp_master hm ON cct.Prescriber_NPI = hm.Prescriber_NPI
        JOIN Payer_Master pm ON cct.payer_id = pm.payer_id
        JOIN Reject_Code_Master rcm ON cct.reject_code = rcm.reject_code
        WHERE cct.claim_status = 'REJECTED'
        ORDER BY cct.claim_amount DESC
        LIMIT 5
    """,
    "Complex Q2 - Specialty Rejection & Financial Exposure": """
        SELECT 
            hm.specialty,
            rcm.severity,
            COUNT(cct.Transaction_ID) as rejected_claims_count,
            SUM(cct.claim_amount) as total_amount_at_risk,
            ROUND(AVG(cct.claim_amount), 2) as avg_claim_amount
        FROM copay_Claims_Transactions cct
        JOIN hcp_master hm ON cct.Prescriber_NPI = hm.Prescriber_NPI
        JOIN Reject_Code_Master rcm ON cct.reject_code = rcm.reject_code
        WHERE cct.claim_status = 'REJECTED'
        GROUP BY hm.specialty, rcm.severity
        ORDER BY total_amount_at_risk DESC
        LIMIT 10
    """,
    "Complex Q3 - Campaign Engagement Efficiency Scorecard": """
        SELECT 
            cm.campaign_name,
            cm.channel,
            cm.budget_amount,
            COUNT(DISTINCT hel.HCP_ID) as targeted_physicians_count,
            SUM(hel.Email_Sent) as total_emails_sent,
            SUM(hel.Email_Opened) as total_emails_opened,
            ROUND(SUM(hel.Email_Opened) / NULLIF(SUM(hel.Email_Sent), 0) * 100, 2) as open_rate_pct,
            SUM(hel.Webinar_Minutes) as total_webinar_minutes
        FROM hcp_engagement_logs hel
        JOIN campaign_master cm ON hel.Campaign_ID = cm.campaign_id
        JOIN hcp_master hm ON hel.HCP_ID = hm.Prescriber_NPI
        GROUP BY cm.campaign_name, cm.channel, cm.budget_amount
        HAVING SUM(hel.Email_Sent) > 0
        ORDER BY open_rate_pct DESC
    """,
    "Complex Q4 - State-Level Leakage & Rejection Breakdown": """
        SELECT 
            la.State,
            COUNT(DISTINCT la.Pharmacy_ID) as distinct_pharmacies,
            COUNT(DISTINCT la.Prescriber_NPI) as distinct_hcps,
            COUNT(DISTINCT la.BrandName) as distinct_brands,
            SUM(la.Pharmacy_Rejections) as total_pharmacy_rejections,
            ROUND(AVG(la.Leakage_Percentage), 2) as avg_leakage_pct,
            MAX(la.Leakage_Percentage) as max_leakage_pct
        FROM Leakage_Activity la
        GROUP BY la.State
        ORDER BY total_pharmacy_rejections DESC
        LIMIT 10
    """,
    "Complex Q5 - Compliance Violations by Payer Region and Type": """
        SELECT 
            pm.region,
            pm.payer_type,
            COUNT(ct.id) as violation_count,
            COUNT(DISTINCT ct.Payer_id) as distinct_payers_affected,
            MIN(ct.Created_At) as earliest_violation,
            MAX(ct.Created_At) as latest_violation
        FROM Compliance_Table ct
        JOIN Payer_Master pm ON ct.Payer_id = pm.payer_id
        GROUP BY pm.region, pm.payer_type
        ORDER BY violation_count DESC
    """
}

for title, sql in queries.items():
    print(f"\n{'='*70}\n{title}\n{'='*70}")
    try:
        res = json.loads(db.execute_sql(sql))
        recs = res.get('records', [])
        print(f"Returned {len(recs)} records:")
        for r in recs[:3]:
            print(f"  {r}")
    except Exception as e:
        print(f"ERROR: {e}")
