from app.services.mysql_service import MySQLService
from app.config import settings
import json

db = MySQLService(
    host=settings.MYSQL_HOST,
    port=settings.MYSQL_PORT,
    user=settings.MYSQL_USER,
    password=settings.MYSQL_PASSWORD,
    database=settings.MYSQL_DATABASE
)

tables = [
    'Reverse_Claims', 'Leakage_Activity', 'Product_Master', 'hcp_master',
    'Compliance_Table', 'fatigue_score', 'hcp_engagement_logs', 'campaign_master',
    'Payer_Master', 'leakage_history', 'Zip_Geography_Master', 'copay_Claims_Transactions',
    'routing_config', 'territory_master', 'Reject_Code_Master'
]

print("=" * 60)
print("TABLE ROW COUNTS")
print("=" * 60)
for t in tables:
    try:
        result = json.loads(db.execute_sql(f"SELECT COUNT(*) as cnt FROM `{t}`"))
        cnt = result.get('records', [{}])[0].get('cnt', 0)
        print(f"  {t}: {cnt} rows")
    except Exception as e:
        print(f"  {t}: ERROR - {e}")

print("\n" + "=" * 60)
print("REVERSE_CLAIMS SAMPLE (3 rows)")
print("=" * 60)
result = json.loads(db.execute_sql("SELECT * FROM Reverse_Claims LIMIT 3"))
for r in result.get('records', []):
    print(f"  {r}")

print("\n" + "=" * 60)
print("LEAKAGE_ACTIVITY SAMPLE (3 rows)")
print("=" * 60)
result = json.loads(db.execute_sql("SELECT * FROM Leakage_Activity LIMIT 3"))
for r in result.get('records', []):
    print(f"  {r}")

print("\n" + "=" * 60)
print("PRODUCT_MASTER SAMPLE (3 rows)")
print("=" * 60)
result = json.loads(db.execute_sql("SELECT * FROM Product_Master LIMIT 3"))
for r in result.get('records', []):
    print(f"  {r}")

print("\n" + "=" * 60)
print("ROUTING_CONFIG COLUMNS")
print("=" * 60)
result = json.loads(db.describe_table("routing_config"))
for col in result.get('columns', []):
    print(f"  {col}")

print("\n" + "=" * 60)
print("TERRITORY_MASTER COLUMNS")
print("=" * 60)
result = json.loads(db.describe_table("territory_master"))
for col in result.get('columns', []):
    print(f"  {col}")

print("\n" + "=" * 60)
print("REJECT_CODE_MASTER COLUMNS")
print("=" * 60)
result = json.loads(db.describe_table("Reject_Code_Master"))
for col in result.get('columns', []):
    print(f"  {col}")

# Check JOIN compatibility
print("\n" + "=" * 60)
print("JOIN TEST: Reverse_Claims x Leakage_Activity ON Prescriber_NPI")
print("=" * 60)
result = json.loads(db.execute_sql(
    "SELECT COUNT(*) as cnt FROM Reverse_Claims rc "
    "JOIN Leakage_Activity la ON rc.Prescriber_NPI = la.Prescriber_NPI LIMIT 1"
))
print(f"  Matching rows: {result.get('records', [{}])[0].get('cnt', 0)}")

print("\n" + "=" * 60)
print("JOIN TEST: Reverse_Claims x Product_Master ON NDC_Code")
print("=" * 60)
result = json.loads(db.execute_sql(
    "SELECT COUNT(*) as cnt FROM Reverse_Claims rc "
    "JOIN Product_Master pm ON rc.NDC_Code = pm.ndc_code LIMIT 1"
))
print(f"  Matching rows: {result.get('records', [{}])[0].get('cnt', 0)}")

print("\n" + "=" * 60)
print("LEAKAGE_ACTIVITY DISTINCT STATES")
print("=" * 60)
result = json.loads(db.execute_sql("SELECT DISTINCT State FROM Leakage_Activity ORDER BY State"))
states = [r.get('State') for r in result.get('records', [])]
print(f"  States: {states}")
