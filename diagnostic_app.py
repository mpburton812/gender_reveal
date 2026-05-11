import streamlit as st
import libsql_client

st.title("Turso Connection Diagnostic")

try:
    url = st.secrets["turso"]["url"]
    token = st.secrets["turso"]["auth_token"]
    
    st.write(f"**Attempting to connect to:** `{url}`")
    
    if url.startswith("libsql://") or url.startswith("wss://"):
        st.warning("⚠️ WebSocket detected. This often causes 505 errors on this specific AWS endpoint.")
    
    client = libsql_client.create_client_sync(url=url, auth_token=token)
    result = client.execute("SELECT 1")
    st.success(f"✅ Connection successful! Result: {result.rows}")
    client.close()
    
except Exception as e:
    st.error(f"### Connection Failed\n{e}")
    st.info("If the URL above shows `wss://` but you set `https://`, check for conflicting environment variables or secrets files.")
