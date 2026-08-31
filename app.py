import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
from fpl_api import (
    PRISON_LEAGUE_ID,
    calculate_weekly_prison_tokens,
    get_latest_gameweek,
    get_league_data,
    get_league_name,
    get_league_title,
    get_global_top_player_selections,
    get_summary_columns,
    get_weekly_overview,
)

st.set_page_config(page_title="FPL League Dashboard", layout="wide")


@st.cache_data(ttl=300)
def load_global_top_player_selections(gameweek):
    return get_global_top_player_selections(gameweek)


if "page" not in st.session_state:
    st.session_state.page = "league"

if st.sidebar.button("Top Players", use_container_width=True):
    st.session_state.page = "top_players"

if st.session_state.page == "top_players":
    st.title("Top Players")
    if st.sidebar.button("Back to League Dashboard", use_container_width=True):
        st.session_state.page = "league"
        st.rerun()

    password = st.text_input("Password", type="password")
    if password != "pw123":
        if password:
            st.error("Incorrect password.")
        else:
            st.info("Enter the password to view global top 100 player selections.")
        st.stop()

    latest_gameweek = get_latest_gameweek()
    st.caption(f"Selections from the global top 100 managers, gameweek {latest_gameweek}")
    with st.spinner("Fetching global top 100 selections..."):
        top_players_df = load_global_top_player_selections(latest_gameweek)

    st.dataframe(
        top_players_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Player Name": st.column_config.TextColumn("Player Name", pinned=True),
            "Club": st.column_config.TextColumn("Club"),
            "Position": st.column_config.TextColumn("Position"),
            "No. of Selections": st.column_config.NumberColumn(
                "No. of Selections",
                format="%d",
            ),
        },
    )
    st.stop()

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

    for player_name, player_df in df.groupby("Player", sort=True):
        row = {
            "Player Name": player_name,
            "Club": player_df["Club"].dropna().iloc[0] if not player_df["Club"].dropna().empty else "",
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

    if not rows:
        return pd.DataFrame(columns=["Player Name", "Club", "No. of Selections"] + manager_columns)

    heatmap_df = pd.DataFrame(rows, columns=["Player Name", "Club", "No. of Selections"] + manager_columns)
    heatmap_df = heatmap_df.sort_values(["No. of Selections", "Player Name"], ascending=[False, True]).reset_index(drop=True)
    return heatmap_df


def flatten_weekly_overview_columns(df):
    if df.empty:
        return df.copy()

    renamed = {}
    for column in df.columns:
        if isinstance(column, tuple):
            label = " / ".join(str(part).strip() for part in column if str(part).strip())
            if column == ('Summary', '', 'Team Member'):
                label = 'Team Member'
            renamed[column] = label
        else:
            renamed[column] = str(column)

    return df.rename(columns=renamed)


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
league_id = st.sidebar.number_input("League ID", value=PRISON_LEAGUE_ID, step=1)
selected_gw = st.sidebar.slider("Gameweek", min_value=1, max_value=38, value=latest_gameweek)
league_name = get_league_name(league_id) or "League"

# Load Data with Spinner
with st.spinner("Fetching data from Fantasy Premier League API..."):
    df = load_data(league_id, selected_gw)

if df.empty:
    st.warning("No data found for this League ID and Gameweek.")
else:
    header_left, header_center, header_right = st.columns([1, 2, 1])
    with header_center:
        st.markdown(
            f"<h1 style='text-align: center;'>{get_league_title(league_id, league_name)}</h1>",
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
    base_summary_cols = ['Manager Name', 'Team Name', 'Team GW Points', 'Transfers Made', 'Card Used']
    summary_df = df[base_summary_cols].drop_duplicates().sort_values(
        by='Team GW Points', ascending=False
    ).reset_index(drop=True)
    summary_df['Ranking'] = summary_df['Team GW Points'].rank(
        method='dense', ascending=False
    ).astype(int)

    if league_id == PRISON_LEAGUE_ID:
        summary_df['Prison token'] = calculate_weekly_prison_tokens(summary_df['Ranking'])

    display_summary_cols = ['Ranking', 'Manager Name', 'Team Name', 'Team GW Points']
    if league_id == PRISON_LEAGUE_ID:
        display_summary_cols.append('Prison token')
    display_summary_cols.extend(['Transfers Made', 'Card Used'])
    summary_df = summary_df[display_summary_cols]
    st.dataframe(
        summary_df,
        width="stretch",
        hide_index=True,
        column_config={
            'Ranking': st.column_config.NumberColumn('Ranking', pinned=True),
            'Manager Name': st.column_config.TextColumn('Manager Name', pinned=True),
        },
    )

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
                if col in ["Player Name", "Club", "No. of Selections"]:
                    continue
                cell_value = row[col]
                if cell_value == "1":
                    styles[idx] = "background-color: #7bc67b; color: #0b5e2c; font-weight: bold;"
            return styles

        heatmap_display = heatmap_df[
            ["Player Name", "Club", "No. of Selections"] + manager_order
        ]

        st.dataframe(
            heatmap_display.style.apply(selection_style, axis=1),
            width="stretch",
            hide_index=True,
            column_config={
                'Player Name': st.column_config.TextColumn('Player Name', pinned=True),
                'No. of Selections': st.column_config.NumberColumn('No. of Selections', pinned=True),
            },
        )

    if league_id == PRISON_LEAGUE_ID:
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

        display_df = flatten_weekly_overview_columns(display_df)
        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
            column_config={
                'Team Member': st.column_config.TextColumn('Team Member', pinned=True),
            },
        )
