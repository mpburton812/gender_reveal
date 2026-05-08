import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# Page configuration
st.set_page_config(page_title="Gender Reveal Media Explorer", layout="wide")

st.title("Gender Reveal Media Explorer")
st.markdown("Explore media mentioned in the *Gender Reveal* podcast. Data is live-synced from Google Sheets.")

# Load data with caching
@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    # Using the Sheet ID from extract_media.py
    url = "https://docs.google.com/spreadsheets/d/1lKL7VkZoLxbrLbX2bVyF8wdb8bxXxBbJGgoQSg7OVUU/edit"
    df = conn.read(spreadsheet=url)
    
    # Ensure episode_number is numeric for better sorting
    if 'episode_number' in df.columns:
        df['episode_number'] = pd.to_numeric(df['episode_number'], errors='coerce')
    return df

try:
    df = load_data()

    # Sidebar Filters
    st.sidebar.header("Filters")

    # Search box
    search_query = st.sidebar.text_input("Search Media or Guest", "")

    # Multi-select filters
    if 'season' in df.columns:
        seasons = sorted(df['season'].dropna().unique())
        selected_seasons = st.sidebar.multiselect("Season", seasons, default=seasons)
    else:
        selected_seasons = []

    if 'media_type' in df.columns:
        media_types = sorted(df['media_type'].dropna().unique())
        selected_types = st.sidebar.multiselect("Media Type", media_types, default=media_types)
    else:
        selected_types = []

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
        col2.metric("Unique Media Items", filtered_df['media_name'].nunique())
    if 'episode_number' in df.columns:
        col3.metric("Episodes Covered", filtered_df['episode_number'].nunique())

    # Data Table
    column_config = {}
    if 'url_to_media' in df.columns:
        column_config["url_to_media"] = st.column_config.LinkColumn("Link")
    if 'episode_number' in df.columns:
        column_config["episode_number"] = st.column_config.NumberColumn("Ep #", format="%d")

    st.dataframe(
        filtered_df,
        column_config=column_config,
        hide_index=True,
        use_container_width=True
    )

    # Refresh Button
    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

except Exception as e:
    st.error(f"Error connecting to Google Sheets: {e}")
    st.info("Ensure your Streamlit Secrets are configured correctly with the service account JSON.")
