import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# Page configuration
st.set_page_config(page_title="Gender Reveal Media Explorer", layout="wide")

st.title("Gender Reveal Media Explorer")
st.markdown("Explore media mentioned in the *Gender Reveal* podcast.")

# Load data with caching
@st.cache_data(ttl=600)
def load_data():
    try:
        # Check if secrets exist
        if "connections" not in st.secrets or "gsheets" not in st.secrets.connections:
            st.error("Secrets for 'gsheets' not found. Please check your Streamlit Cloud Secrets.")
            return None
            
        # Get email for debugging
        creds = st.secrets.connections.gsheets
        email = creds.get("client_email") or creds.get("service_account", {}).get("client_email")
        
        st.write(f"**Debug:** Attempting connection using: `{email}`")
        
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read()
        
        if df is None or df.empty:
            st.error("The Google Sheet appears to be empty or unreachable.")
            return None

        if 'episode_number' in df.columns:
            df['episode_number'] = pd.to_numeric(df['episode_number'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"### Connection Error\n{e}")
        
        # Try to extract the email again for the error message
        try:
            creds = st.secrets.connections.gsheets
            email = creds.get("client_email") or creds.get("service_account", {}).get("client_email")
        except:
            email = "the service account email"

        st.info(f"""
        **Troubleshooting Steps:**
        1. **Check Sharing:** Ensure your Google Sheet is shared with:  
           `{email}`  
           (Set to **Editor**)
        2. **Check Key Format:** Ensure your `private_key` in Secrets has actual line breaks (see `streamlit_secrets_template.toml`).
        """)
        return None

df = load_data()

if df is not None:
    # Sidebar Filters
    st.sidebar.header("Filters")
    search_query = st.sidebar.text_input("Search Media or Guest", "")

    # Multi-select filters
    seasons = sorted(df['season'].dropna().unique()) if 'season' in df.columns else []
    selected_seasons = st.sidebar.multiselect("Season", seasons, default=seasons)

    media_types = sorted(df['media_type'].dropna().unique()) if 'media_type' in df.columns else []
    selected_types = st.sidebar.multiselect("Media Type", media_types, default=media_types)

    # Filtering logic
    filtered_df = df.copy()
    if 'season' in df.columns:
        filtered_df = filtered_df[filtered_df['season'].isin(selected_seasons)]
    if 'media_type' in df.columns:
        filtered_df = filtered_df[filtered_df['media_type'].isin(selected_types)]

    if search_query:
        query = search_query.lower()
        search_cols = [c for c in ['media_name', 'guest', 'media_sub_category'] if c in df.columns]
        if search_cols:
            mask = filtered_df[search_cols].apply(lambda x: x.str.lower().str.contains(query, na=False)).any(axis=1)
            filtered_df = filtered_df[mask]

    # Display stats
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Mentions", len(filtered_df))
    if 'media_name' in df.columns:
        col2.metric("Unique Items", filtered_df['media_name'].nunique())
    if 'episode_number' in df.columns:
        col3.metric("Episodes", filtered_df['episode_number'].nunique())

    # Data Table
    st.dataframe(
        filtered_df,
        column_config={
            "url_to_media": st.column_config.LinkColumn("Link"),
            "episode_number": st.column_config.NumberColumn("Ep #", format="%d"),
        },
        hide_index=True,
        use_container_width=True
    )

    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()
