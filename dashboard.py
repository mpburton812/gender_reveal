import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import urllib.parse

# --- UTILS ---

def get_bookshop_link(title):
    """Generates a search link for Bookshop.org."""
    query = urllib.parse.quote(title)
    return f"https://bookshop.org/search?keywords={query}"

def get_letterboxd_link(title):
    """Generates a search link for Letterboxd."""
    query = urllib.parse.quote(title)
    return f"https://letterboxd.com/search/{query}/"

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
    with st.sidebar:
        st.title("Settings & Support")
        
        st.markdown("### 💖 Support the Show")
        st.info("Gender Reveal is a non-profit podcast that relies on listener support.")
        st.link_button("Join our Patreon", "https://www.patreon.com/gender", use_container_width=True)
        st.link_button("Official Merch Shop", "https://bit.ly/gendermerch", use_container_width=True)
        
        st.markdown("---")
        st.header("Search")
        search_query = st.text_input("Find any book, guest, or topic...", "")

        st.markdown("---")
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Filtering logic
    filtered_df = df.copy()

    if search_query:
        query = search_query.lower()
        # Global search across all columns
        mask = filtered_df.astype(str).apply(lambda x: x.str.lower().str.contains(query, na=False)).any(axis=1)
        filtered_df = filtered_df[mask]

    # Display stats (Global)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Mentions", len(filtered_df))
    if 'media_name' in df.columns:
        col2.metric("Unique Items", filtered_df['media_name'].nunique())
    if 'episode_number' in df.columns:
        col3.metric("Episodes", filtered_df['episode_number'].nunique())

    # --- TABS ---
    tab1, tab2, tab3 = st.tabs(["🎙️ Episode Media References", "🖼️ Visual Gallery", "📚 Most Mentioned Media"])

    with tab1:
        # Data Table (Existing)
        st.dataframe(
            filtered_df,
            column_config={
                "image_url": st.column_config.ImageColumn("Cover", help="Media Cover Art"),
                "url_to_media": st.column_config.LinkColumn("Link"),
                "episode_number": st.column_config.NumberColumn("Ep #", format="%d"),
                "episode_url": st.column_config.LinkColumn("Listen to Ep"),
                "mention_context": st.column_config.TextColumn("Context", width="large"),
            },
            hide_index=True,
            use_container_width=True
        )

        # Detailed Search / Discovery Section (Existing)
        st.markdown("---")
        st.subheader("Media Spotlight")
        st.info("Click on a row in the table above to see more details, or use the search box to find specific mentions.")

    with tab2:
        st.subheader("Media Library")
        st.markdown("A visual collection of media mentioned on the show.")
        
        # Only show items that have images for the gallery
        gallery_df = filtered_df[filtered_df['image_url'].notna() & (filtered_df['image_url'] != "")]
        
        if gallery_df.empty:
            st.info("No media with cover art found in the current selection. Try running an enrichment batch or selecting different filters.")
        else:
            # Create a responsive grid (4 columns on wide screens)
            cols_per_row = 4
            for i in range(0, len(gallery_df), cols_per_row):
                cols = st.columns(cols_per_row)
                for j in range(cols_per_row):
                    if i + j < len(gallery_df):
                        item = gallery_df.iloc[i + j]
                        with cols[j]:
                            st.image(item['image_url'], use_container_width=True)
                            st.markdown(f"**{item['media_name']}**")
                            st.caption(f"{item['media_type'].title()} • Ep {item['episode_number']}")
                            
                            with st.expander("Details"):
                                st.write(item.get('mention_context', "No context available."))
                                if pd.notna(item.get('episode_url')) and item['episode_url']:
                                    st.link_button("🎧 Listen", item['episode_url'], use_container_width=True)
                                
                                # Support Links
                                m_type = str(item.get('media_type', '')).lower()
                                m_name = str(item.get('media_name', ''))
                                if 'book' in m_type or 'graphic novel' in m_type:
                                    st.link_button("🛒 Buy", get_bookshop_link(m_name), use_container_width=True)
                                elif 'movie' in m_type or 'tv show' in m_type:
                                    st.link_button("📽️ View", get_letterboxd_link(m_name), use_container_width=True)

    with tab3:
        st.subheader("Most Mentioned Media")
        st.markdown("Items grouped by popularity across all selected episodes.")
        
        if not filtered_df.empty:
            # Grouping Logic
            favs = filtered_df.groupby(['media_name', 'media_type']).agg({
                'guest': lambda x: ", ".join(sorted(list(set([str(val) for val in x if pd.notna(val) and val != ""])))),
                'image_url': 'first', # Take the first available cover
                'url_to_media': 'first',
                'season': 'count' # Use as mention count
            }).reset_index()
            
            favs = favs.rename(columns={'season': 'mentions', 'guest': 'recommended_by'})
            favs = favs.sort_values(by='mentions', ascending=False)

            st.dataframe(
                favs,
                column_config={
                    "image_url": st.column_config.ImageColumn("Cover"),
                    "mentions": st.column_config.NumberColumn("Mentions", format="%d 🔥"),
                    "recommended_by": st.column_config.TextColumn("Recommended By", width="large"),
                    "url_to_media": st.column_config.LinkColumn("Link"),
                },
                hide_index=True,
                use_container_width=True
            )
    
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
                
                # Podcast Link
                if pd.notna(row.get('episode_url')) and row['episode_url']:
                    st.link_button("🎧 Listen to Episode", row['episode_url'], use_container_width=True)

                # Support / Discovery Links
                m_type = str(row.get('media_type', '')).lower()
                m_name = str(row.get('media_name', ''))
                
                if 'book' in m_type or 'graphic novel' in m_type:
                    st.link_button("🛒 Buy on Bookshop", get_bookshop_link(m_name), use_container_width=True)
                elif 'movie' in m_type or 'tv show' in m_type:
                    st.link_button("📽️ View on Letterboxd", get_letterboxd_link(m_name), use_container_width=True)
                
                if pd.notna(row.get('url_to_media')) and row['url_to_media']:
                    st.caption(f"[Canonical Link]({row['url_to_media']})")
