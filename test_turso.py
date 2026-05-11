import libsql_client
import os
from dotenv import load_dotenv

# Load local .env
load_dotenv()

url_env = os.getenv("TURSO_DATABASE_URL")
token_env = os.getenv("TURSO_AUTH_TOKEN")

print("--- TURSO CONNECTION TEST ---")
print(f"Env URL: {url_env}")

def test_url(url, token):
    print(f"\nTesting: {url}")
    try:
        client = libsql_client.create_client_sync(url=url, auth_token=token)
        result = client.execute("SELECT 1")
        print("✅ SUCCESS!")
        print(f"   Result: {result.rows}")
        client.close()
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False

# 1. Test from .env
if url_env and token_env:
    test_url(url_env, token_env)

# 2. Test explicit HTTPS (Recommended)
url_https = "https://genderreveal-mpburton.aws-us-east-2.turso.io"
test_url(url_https, token_env)

# 3. Test explicit libsql (Might fail with 505)
url_libsql = "libsql://genderreveal-mpburton.aws-us-east-2.turso.io"
test_url(url_libsql, token_env)

print("\n--- CONCLUSION ---")
print("If HTTPS works but libsql/wss fails with 505:")
print("1. Use 'https://' in your .env and Streamlit Cloud Secrets.")
print("2. Ensure you are NOT using client.transaction() with the HTTP client.")
print("3. Use client.batch() for multiple operations over HTTP.")
