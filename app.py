import streamlit as st
import pandas as pd
from fpl_api import (
    calculate_weekly_prison_tokens,
    get_latest_gameweek,
    get_league_data,
    get_weekly_overview,
)

st.set_page_config(page_title="FPL League Dashboard", layout="wide")

ROUND_GROUPS = {
    1: [1, 2, 3, 4],
    2: [5, 6, 7, 8],
    3: [9, 10, 11, 12],
    4: [13, 14, 15, 16],
    5: [17, 18, 19, 20],
    6: [21, 22, 23, 24],
    7: [25, 26, 27, 28],
    8: [29, 30, 31, 32],
    9: [33, 34, 35, 36, 37, 38],
}


def get_round_for_gameweek(gameweek):
    for round_no, weeks in ROUND_GROUPS.items():
        if gameweek in weeks:
            return round_no
    return 1


def build_player_selection_heatmap(df, manager_order):
    if df.empty:
        return pd.DataFrame()

    manager_columns = list(manager_order)
    rows = []
    selection_counts = {}

    for player_name, player_df in df.groupby("Player", sort=True):
        row = {
            "Player Name": player_name,
            "Club": player_df["Club"].dropna().iloc[0] if not player_df["Club"].dropna().empty else "",
            "Position": player_df["Position"].dropna().iloc[0] if not player_df["Position"].dropna().empty else "",
        }

        selection_count = 0
        for manager_name in manager_columns:
            manager_pick = player_df[player_df["Manager Name"] == manager_name]
            if manager_pick.empty:
                row[manager_name] = ""
                continue

            pick = manager_pick.iloc[0]
            row[manager_name] = "1" if not pd.isna(pick["Player"]) else ""
            selection_count += 1

        row["No. of Selections"] = selection_count
        rows.append(row)
        selection_counts[player_name] = selection_count

    if not rows:
        return pd.DataFrame(columns=["Player Name", "Club", "Position", "No. of Selections"] + manager_columns)

    heatmap_df = pd.DataFrame(rows, columns=["Player Name", "Club", "Position", "No. of Selections"] + manager_columns)
    return heatmap_df


@st.cache_data(ttl=300)
def load_data(league_id, gw):
    return get_league_data(league_id, gw)

@st.cache_data(ttl=300)
def load_weekly_overview(league_id):
    return get_weekly_overview(league_id)

latest_gameweek = get_latest_gameweek()
latest_round = get_round_for_gameweek(latest_gameweek)

# Sidebar Controls
st.sidebar.header("League Controls")
league_id = st.sidebar.number_input("League ID", value=185376, step=1)
selected_gw = st.sidebar.slider("Gameweek", min_value=1, max_value=38, value=latest_gameweek)

# Load Data with Spinner
with st.spinner("Fetching data from Fantasy Premier League API..."):
    df = load_data(league_id, selected_gw)

if df.empty:
    st.warning("No data found for this League ID and Gameweek.")
else:
    header_left, header_center, header_right = st.columns([1, 2, 1])
    with header_center:
        st.markdown(
            "<h1 style='text-align: center;'>Prison Breaker FPL 26/27</h1>",
            unsafe_allow_html=True,
        )
    with header_right:
        gameweek_status = df['Gameweek Status'].iloc[0]
        st.markdown(
            f"<div style='text-align: right; padding-top: 1rem;'><strong>Game week {selected_gw} status</strong><br>{gameweek_status}</div>",
            unsafe_allow_html=True,
        )
    
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

    summary_df['Prison token'] = calculate_weekly_prison_tokens(summary_df['Ranking'])
    summary_df = summary_df[
        ['Ranking', 'Manager Name', 'Team Name', 'Team GW Points',
         'Prison token', 'Transfers Made', 'Card Used']
    ]
    st.dataframe(summary_df, width="stretch", hide_index=True)

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
            width="stretch"
        )
    with col_bench:
        st.markdown("**Bench**")
        st.dataframe(
            bench[['Player', 'Position', 'Club', 'Opponent', 'Opponent Difficulty', 'Player Points']], 
            hide_index=True, 
            width="stretch"
        )

    st.subheader("🎯 Selected Player Heatmap")
    manager_order = summary_df['Manager Name'].tolist()
    heatmap_df = build_player_selection_heatmap(df, manager_order)

    if not heatmap_df.empty:
        def selection_style(row):
            styles = ["" for _ in row]
            for idx, col in enumerate(row.index):
                if col in ["Player Name", "Club", "Position", "No. of Selections"]:
                    continue
                cell_value = row[col]
                if cell_value == "1":
                    styles[idx] = "background-color: #7bc67b; color: #0b5e2c; font-weight: bold;"
            return styles

        st.dataframe(
            heatmap_df.style.apply(selection_style, axis=1),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("📅 Weekly Overview")
    with st.spinner("Loading weekly results..."):
        weekly_overview_df = load_weekly_overview(league_id)

    round_options = [0] + list(range(1, 10))
    default_round_index = round_options.index(latest_round)
    selected_round = st.selectbox(
        "Display Round",
        options=round_options,
        index=default_round_index,
        format_func=lambda value: "All Rounds" if value == 0 else f"Round {value}",
    )

    if selected_round == 0:
        display_df = weekly_overview_df
    else:
        selected_round_label = f"Round {selected_round}"
        display_cols = [
            col for col in weekly_overview_df.columns
            if col in [
                ('Summary', '', 'Team Member'),
                ('Summary', '', 'Total Scores'),
                ('Summary', '', 'Total Prison Tokens'),
            ]
            or (isinstance(col, tuple) and len(col) == 3 and col[0] == selected_round_label)
        ]
        display_df = weekly_overview_df[display_cols]

    st.dataframe(display_df, width="stretch", hide_index=True)
