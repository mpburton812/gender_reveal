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
        conn = st.connection("gsheets", type=GSheetsConnection)
        url = "https://docs.google.com/spreadsheets/d/1lKL7VkZoLxbrLbX2bVyF8wdb8bxXxBbJGgoQSg7OVUU/edit"
        df = conn.read(spreadsheet=url)
        
        if df is None or df.empty:
            st.error("The Google Sheet appears to be empty or unreachable.")
            return None

        # Ensure episode_number is numeric
        if 'episode_number' in df.columns:
            df['episode_number'] = pd.to_numeric(df['episode_number'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"### Connection Error\n{e}")
        st.info("""
        **Troubleshooting Steps:**
        1. **Share the Sheet:** Open your Google Sheet, click **Share**, and add this email as an **Editor**:
           `service-account-2@gender-reveal-494314.iam.gserviceaccount.com`
        2. **Check Secrets:** Ensure your Streamlit Cloud Secrets are formatted correctly (see `streamlit_secrets_template.toml`).
        3. **Wait 1 minute:** Sometimes Streamlit takes a moment to update secrets.
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
