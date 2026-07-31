import json
from app.config import settings
from app.services.mysql_service import MySQLService

db_service = MySQLService(
    host=settings.MYSQL_HOST,
    port=settings.MYSQL_PORT,
    user=settings.MYSQL_USER,
    password=settings.MYSQL_PASSWORD,
    database=settings.MYSQL_DATABASE
)

print("Listing all MySQL tables:")
print(db_service.list_tables())

print("\n" + "="*40 + "\n")

print("Describing 'users' table:")
print(db_service.describe_table("users"))

print("\n" + "="*40 + "\n")

print("Describing 'orders' table:")
print(db_service.describe_table("orders"))
