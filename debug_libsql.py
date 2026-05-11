import libsql_client
import os
from dotenv import load_dotenv

load_dotenv(override=True)
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

print(f"URL: {url}")
client = libsql_client.create_client_sync(url=url, auth_token=token)
result = client.execute("SELECT 1 as test")
print(f"Type of result: {type(result)}")
print(f"Attributes: {dir(result)}")
try:
    print(f"Rows: {result.rows}")
    print(f"Columns: {result.columns}")
except Exception as e:
    print(f"Error accessing result attributes: {e}")
client.close()
