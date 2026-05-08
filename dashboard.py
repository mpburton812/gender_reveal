import streamlit as st
import pandas as pd

# Page configuration
st.set_page_config(page_title="Gender Reveal Media Explorer", layout="wide")

st.title("Gender Reveal Media Explorer")
st.markdown("Explore media mentioned in the *Gender Reveal* podcast.")

# Load data with caching
@st.cache_data
def load_data():
    df = pd.read_csv("extracted_media.csv")
    # Ensure episode_number is numeric for better sorting
    df['episode_number'] = pd.to_numeric(df['episode_number'], errors='coerce')
    return df

try:
    df = load_data()

    # Sidebar Filters
    st.sidebar.header("Filters")

    # Search box
    search_query = st.sidebar.text_input("Search Media or Guest", "")

    # Multi-select filters
    seasons = sorted(df['season'].dropna().unique())
    selected_seasons = st.sidebar.multiselect("Season", seasons, default=seasons)

    media_types = sorted(df['media_type'].dropna().unique())
    selected_types = st.sidebar.multiselect("Media Type", media_types, default=media_types)

    # Filtering logic
    filtered_df = df[
        (df['season'].isin(selected_seasons)) &
        (df['media_type'].isin(selected_types))
    ]

    if search_query:
        query = search_query.lower()
        filtered_df = filtered_df[
            filtered_df['media_name'].str.lower().str.contains(query, na=False) |
            filtered_df['guest'].str.lower().str.contains(query, na=False) |
            filtered_df['media_sub_category'].str.lower().str.contains(query, na=False)
        ]

    # Display stats
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Mentions", len(filtered_df))
    col2.metric("Unique Media Items", filtered_df['media_name'].nunique())
    col3.metric("Episodes Covered", filtered_df['episode_number'].nunique())

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

    # Download option
    csv = filtered_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download filtered data as CSV",
        data=csv,
        file_name='filtered_media.csv',
        mime='text/csv',
    )

except FileNotFoundError:
    st.error("extracted_media.csv not found. Please ensure the file exists in the directory.")
except Exception as e:
    st.error(f"An error occurred: {e}")
