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
        # Simplest possible connection
        # It will automatically find [connections.gsheets] in secrets
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read()
        
        if df is None or df.empty:
            st.warning("The Google Sheet appears to be empty.")
            return None

        if 'episode_number' in df.columns:
            df['episode_number'] = pd.to_numeric(df['episode_number'], errors='coerce')
        
        # Numeric sort for Season and Episode
        def extract_num(val):
            if pd.isna(val) or val == "": return 0
            import re
            match = re.search(r'(\d+)', str(val))
            if match: return float(match.group(1))
            if "bonus" in str(val).lower(): return 999.0
            return 0

        if 'season' in df.columns and 'episode_number' in df.columns:
            df['season_sort'] = df['season'].apply(extract_num)
            df['ep_sort'] = df['episode_number'].apply(extract_num)
            df = df.sort_values(by=['season_sort', 'ep_sort'], ascending=[True, True])
            df = df.drop(columns=['season_sort', 'ep_sort'])
            
        return df
    except Exception as e:
        st.error(f"### Connection Error\n{e}")
        st.info("Check your Streamlit Cloud Secrets against `streamlit_secrets_template.toml` and ensure the Sheet is Shared with your service account email.")
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
            "image_url": st.column_config.ImageColumn("Cover", help="Media Cover Art"),
            "url_to_media": st.column_config.LinkColumn("Link"),
            "episode_number": st.column_config.NumberColumn("Ep #", format="%d"),
            "mention_context": st.column_config.TextColumn("Context", width="large"),
        },
        hide_index=True,
        use_container_width=True
    )

    # Detailed Search / Discovery Section
    st.markdown("---")
    st.subheader("Media Spotlight")
    st.info("Click on a row in the table above to see more details, or use the search box to find specific mentions.")
    
    # Show detailed cards for the first few items in the filtered list
    spotlight_count = min(len(filtered_df), 5)
    if spotlight_count > 0:
        cols = st.columns(spotlight_count)
        for i in range(spotlight_count):
            row = filtered_df.iloc[i]
            with cols[i]:
                if pd.notna(row.get('image_url')) and row['image_url']:
                    st.image(row['image_url'], use_container_width=True)
                else:
                    st.markdown(f"**{row['media_name']}**")
                
                with st.expander("Why was it mentioned?"):
                    st.write(row.get('mention_context', "No context available."))
                    st.caption(f"Mentioned in Ep {row.get('episode_number', '??')}")

    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()
