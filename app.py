import streamlit as st
import pandas as pd
from fpl_api import get_league_data

st.set_page_config(page_title="FPL League Dashboard", layout="wide")

@st.cache_data(ttl=300)
def load_data(league_id, gw):
    return get_league_data(league_id, gw)

# Sidebar Controls
st.sidebar.header("League Controls")
league_id = st.sidebar.number_input("League ID", value=185376, step=1)
selected_gw = st.sidebar.slider("Gameweek", min_value=1, max_value=38, value=1)

# Load Data with Spinner
with st.spinner("Fetching data from Fantasy Premier League API..."):
    df = load_data(league_id, selected_gw)

if df.empty:
    st.warning("No data found for this League ID and Gameweek.")
else:
    st.title(f"🏆 League Dashboard — Gameweek {selected_gw}")
    
    # 1. Weekly Highlights Cards
    top_score = df['Team GW Points'].max()
    top_manager = df[df['Team GW Points'] == top_score]['Manager Name'].iloc[0]
    
    bench_df = df[df['Is Substitute']]
    if not bench_df.empty:
        bench_grouped = bench_df.groupby('Manager Name')['Player Points'].sum()
        bench_pain_mgr = bench_grouped.idxmax()
        bench_pain_pts = bench_grouped.max()
    else:
        bench_pain_mgr, bench_pain_pts = "N/A", 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Gameweek Winner", top_manager, f"{top_score} Pts")
    col2.metric("Bench Pain Award", bench_pain_mgr, f"{bench_pain_pts} Pts on Bench")
    col3.metric("Total Managers", df['Manager Name'].nunique())

    st.markdown("---")

    # 2. League Overview Table
    st.subheader("📊 Manager Standings")
    summary_cols = ['Manager Name', 'Team Name', 'Team GW Points', 'Transfers Made', 'Card Used']
    summary_df = df[summary_cols].drop_duplicates().sort_values(
        by='Team GW Points', ascending=False
    ).reset_index(drop=True)
    summary_df['Ranking'] = summary_df['Team GW Points'].rank(
        method='dense', ascending=False
    ).astype(int)

    contribution_by_rank = {4: 20, 5: 20, 6: 30, 7: 30}
    summary_df['Prison token'] = -summary_df['Ranking'].map(
        contribution_by_rank
    ).fillna(0)
    token_pool = -summary_df['Prison token'].sum()

    rank_one = summary_df['Ranking'] == 1
    rank_two = summary_df['Ranking'] == 2
    summary_df.loc[rank_one, 'Prison token'] = token_pool * 0.7 / rank_one.sum()
    summary_df.loc[rank_two, 'Prison token'] = token_pool * 0.3 / rank_two.sum()

    summary_df['Prison token'] = summary_df['Prison token'].round(2)
    summary_df = summary_df[
        ['Ranking', 'Manager Name', 'Team Name', 'Team GW Points',
         'Transfers Made', 'Card Used', 'Prison token']
    ]
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # 3. Squad Inspector
    st.subheader("🔍 Squad Inspector")
    selected_mgr = st.selectbox("Select Manager", summary_df['Manager Name'].tolist())
    mgr_df = df[df['Manager Name'] == selected_mgr]

    starters = mgr_df[~mgr_df['Is Substitute']]
    bench = mgr_df[mgr_df['Is Substitute']]

    col_start, col_bench = st.columns([3, 2])
    with col_start:
        st.markdown("**Starting XI**")
        st.dataframe(
            starters[['Player', 'Position', 'Club', 'Opponent', 'Opponent Difficulty', 'Player Points', 'Captain Status']], 
            hide_index=True, 
            use_container_width=True
        )
    with col_bench:
        st.markdown("**Bench**")
        st.dataframe(
            bench[['Player', 'Position', 'Club', 'Opponent', 'Opponent Difficulty', 'Player Points']], 
            hide_index=True, 
            use_container_width=True
        )