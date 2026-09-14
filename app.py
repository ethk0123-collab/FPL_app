import os
import sys
import tempfile
from html import escape

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
from fpl_api import (
    PRISON_LEAGUE_ID,
    calculate_weekly_prison_tokens,
    get_global_top_player_minutes_played,
    get_global_top_player_points_by_difficulty,
    get_global_top_player_selections,
    get_global_top_player_weekly_points,
    get_latest_gameweek,
    get_league_data,
    get_league_name,
    get_league_title,
    get_summary_columns,
    get_team_fixture_difficulty_matrix,
    get_weekly_overview,
    dataframe_to_jpeg,
    custom_rank,
)

st.set_page_config(page_title="FPL League Dashboard", layout="wide")


@st.cache_data(ttl=300)
def load_global_top_player_selections(gameweek):
    return get_global_top_player_selections(gameweek)


@st.cache_data(ttl=300)
def load_global_top_player_weekly_points(gameweek):
    return get_global_top_player_weekly_points(gameweek)


@st.cache_data(ttl=300)
def load_global_top_player_minutes_played(gameweek):
    return get_global_top_player_minutes_played(gameweek)


@st.cache_data(ttl=300)
def load_global_top_player_points_by_difficulty(gameweek):
    return get_global_top_player_points_by_difficulty(gameweek)


@st.cache_data(ttl=3600)
def load_team_fixture_difficulty_matrix():
    return get_team_fixture_difficulty_matrix()


FDR_COLORS = {
    1: ('#375523', '#ffffff'),
    2: ('#01fc7a', '#000000'),
    3: ('#e7e7e7', '#000000'),
    4: ('#ff1751', '#ffffff'),
    5: ('#80072d', '#ffffff'),
}


def style_fixture_difficulty_matrix(display_df, difficulty_df):
    def apply_colors(_):
        styles = pd.DataFrame('', index=display_df.index, columns=display_df.columns)
        for col in display_df.columns:
            if col == 'Club':
                continue
            for idx in display_df.index:
                difficulty = difficulty_df.at[idx, col]
                bg_color, text_color = FDR_COLORS.get(int(difficulty), ('#ffffff', '#000000'))
                styles.at[idx, col] = f'background-color: {bg_color}; color: {text_color}'
        return styles

    return display_df.style.apply(apply_colors, axis=None)


def style_weekly_points_matrix(display_df):
    gw_columns = [col for col in display_df.columns if col.startswith('GW')]

    def highlight_high_scores(_):
        styles = pd.DataFrame('', index=display_df.index, columns=display_df.columns)
        for col in gw_columns:
            styles[col] = display_df[col].apply(
                lambda value: 'background-color: #01fc7a' if pd.notna(value) and value > 10 else ''
            )
        return styles

    return display_df.style.apply(highlight_high_scores, axis=None)


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

    st.subheader("Fixture Difficulty Matrix")
    with st.spinner("Fetching fixture difficulty..."):
        fixture_display_df, fixture_difficulty_df = load_team_fixture_difficulty_matrix()

    st.dataframe(
        style_fixture_difficulty_matrix(fixture_display_df, fixture_difficulty_df),
        width="stretch",
        hide_index=True,
        column_config={"Club": st.column_config.TextColumn("Club", pinned=True)},
    )

    if "linked_selected_player" not in st.session_state:
        st.session_state.linked_selected_player = None
        st.session_state.linked_selected_source = None

    if st.session_state.linked_selected_player:
        st.caption(f"Filtering both matrices to player: **{st.session_state.linked_selected_player}**")
        if st.button("Clear player selection"):
            st.session_state.linked_selected_player = None
            st.session_state.linked_selected_source = None
            st.rerun()

    st.subheader("Weekly Points Matrix")
    with st.spinner("Fetching weekly points..."):
        weekly_points_df = load_global_top_player_weekly_points(latest_gameweek)

    position_options = sorted(weekly_points_df["Position"].dropna().unique().tolist())
    selected_positions = st.pills(
        "Position",
        position_options,
        selection_mode="multi",
        default=position_options,
    )

    club_options = ["All"] + sorted(weekly_points_df["Club"].dropna().unique().tolist())
    selected_club = st.selectbox("Club", club_options)

    filtered_weekly_points_df = weekly_points_df[weekly_points_df["Position"].isin(selected_positions)]
    if selected_club != "All":
        filtered_weekly_points_df = filtered_weekly_points_df[filtered_weekly_points_df["Club"] == selected_club]

    if st.session_state.linked_selected_player and st.session_state.linked_selected_source != "weekly":
        filtered_weekly_points_df = filtered_weekly_points_df[
            filtered_weekly_points_df["Player Name"] == st.session_state.linked_selected_player
        ]

    filtered_weekly_points_df = filtered_weekly_points_df.sort_values("Average Points", ascending=False)

    weekly_points_event = st.dataframe(
        style_weekly_points_matrix(filtered_weekly_points_df),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="weekly_points_table",
        column_config={
            "Player Name": st.column_config.TextColumn("Player Name", pinned=True),
            "Club": st.column_config.TextColumn("Club"),
            "Position": st.column_config.TextColumn("Position"),
            "Total Points": st.column_config.NumberColumn("Total Points", format="%d"),
            "Average Points": st.column_config.NumberColumn("Average Points", format="%.2f"),
        },
    )
    weekly_selected_rows = weekly_points_event.selection.rows if weekly_points_event else []
    if weekly_selected_rows:
        st.session_state.linked_selected_player = filtered_weekly_points_df.iloc[weekly_selected_rows[0]]["Player Name"]
        st.session_state.linked_selected_source = "weekly"
    elif st.session_state.linked_selected_source == "weekly":
        st.session_state.linked_selected_player = None
        st.session_state.linked_selected_source = None

    st.subheader("Weekly Points by Difficulty")
    with st.spinner("Fetching weekly points by difficulty..."):
        points_by_difficulty_df = load_global_top_player_points_by_difficulty(latest_gameweek)

    difficulty_position_options = sorted(points_by_difficulty_df["Position"].dropna().unique().tolist())
    selected_difficulty_positions = st.pills(
        "Position",
        difficulty_position_options,
        selection_mode="multi",
        default=difficulty_position_options,
        key="difficulty_position_filter",
    )

    difficulty_club_options = ["All"] + sorted(points_by_difficulty_df["Club"].dropna().unique().tolist())
    selected_difficulty_club = st.selectbox("Club", difficulty_club_options, key="difficulty_club_filter")

    filtered_points_by_difficulty_df = points_by_difficulty_df[
        points_by_difficulty_df["Position"].isin(selected_difficulty_positions)
    ]
    if selected_difficulty_club != "All":
        filtered_points_by_difficulty_df = filtered_points_by_difficulty_df[
            filtered_points_by_difficulty_df["Club"] == selected_difficulty_club
        ]

    if st.session_state.linked_selected_player and st.session_state.linked_selected_source != "difficulty":
        filtered_points_by_difficulty_df = filtered_points_by_difficulty_df[
            filtered_points_by_difficulty_df["Player Name"] == st.session_state.linked_selected_player
        ]

    filtered_points_by_difficulty_df = filtered_points_by_difficulty_df.sort_values("Average Points", ascending=False)

    difficulty_number_columns = {
        "Total Points": st.column_config.NumberColumn("Total Points", format="%d"),
        "Average Points": st.column_config.NumberColumn("Average Points", format="%.2f"),
    }
    for level in range(1, 6):
        difficulty_number_columns[f"Total Pts (FDR {level})"] = st.column_config.NumberColumn(
            f"Total Pts (FDR {level})", format="%d"
        )
        difficulty_number_columns[f"Avg Pts (FDR {level})"] = st.column_config.NumberColumn(
            f"Avg Pts (FDR {level})", format="%.2f"
        )

    points_by_difficulty_event = st.dataframe(
        filtered_points_by_difficulty_df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="points_by_difficulty_table",
        column_config={
            "Player Name": st.column_config.TextColumn("Player Name", pinned=True),
            "Club": st.column_config.TextColumn("Club"),
            "Position": st.column_config.TextColumn("Position"),
            **difficulty_number_columns,
        },
    )
    difficulty_selected_rows = points_by_difficulty_event.selection.rows if points_by_difficulty_event else []
    if difficulty_selected_rows:
        st.session_state.linked_selected_player = filtered_points_by_difficulty_df.iloc[difficulty_selected_rows[0]]["Player Name"]
        st.session_state.linked_selected_source = "difficulty"
    elif st.session_state.linked_selected_source == "difficulty":
        st.session_state.linked_selected_player = None
        st.session_state.linked_selected_source = None

    st.subheader("Minutes Played Overview")
    with st.spinner("Fetching minutes played..."):
        minutes_played_df = load_global_top_player_minutes_played(latest_gameweek)

    minutes_position_options = sorted(minutes_played_df["Position"].dropna().unique().tolist())
    selected_minutes_positions = st.pills(
        "Position",
        minutes_position_options,
        selection_mode="multi",
        default=minutes_position_options,
        key="minutes_position_filter",
    )

    minutes_club_options = ["All"] + sorted(minutes_played_df["Club"].dropna().unique().tolist())
    selected_minutes_club = st.selectbox("Club", minutes_club_options, key="minutes_club_filter")

    filtered_minutes_played_df = minutes_played_df[minutes_played_df["Position"].isin(selected_minutes_positions)]
    if selected_minutes_club != "All":
        filtered_minutes_played_df = filtered_minutes_played_df[filtered_minutes_played_df["Club"] == selected_minutes_club]

    if st.session_state.linked_selected_player and st.session_state.linked_selected_source != "minutes":
        filtered_minutes_played_df = filtered_minutes_played_df[
            filtered_minutes_played_df["Player Name"] == st.session_state.linked_selected_player
        ]

    filtered_minutes_played_df = filtered_minutes_played_df.sort_values("Total Minutes", ascending=False)

    minutes_played_event = st.dataframe(
        filtered_minutes_played_df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="minutes_played_table",
        column_config={
            "Player Name": st.column_config.TextColumn("Player Name", pinned=True),
            "Club": st.column_config.TextColumn("Club"),
            "Position": st.column_config.TextColumn("Position"),
            "Total Minutes": st.column_config.NumberColumn("Total Minutes", format="%d"),
            "# of Match >0 min": st.column_config.NumberColumn("# of Match >0 min", format="%d"),
        },
    )
    minutes_selected_rows = minutes_played_event.selection.rows if minutes_played_event else []
    if minutes_selected_rows:
        st.session_state.linked_selected_player = filtered_minutes_played_df.iloc[minutes_selected_rows[0]]["Player Name"]
        st.session_state.linked_selected_source = "minutes"
    elif st.session_state.linked_selected_source == "minutes":
        st.session_state.linked_selected_player = None
        st.session_state.linked_selected_source = None
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

    flattened_columns = []
    for column in df.columns:
        if isinstance(column, tuple):
            label = " / ".join(str(part).strip() for part in column if str(part).strip())
            if column == ('Summary', '', 'Team Member'):
                label = 'Team Member'
            flattened_columns.append(label)
        else:
            flattened_columns.append(str(column))

    flattened = df.copy()
    flattened.columns = flattened_columns
    return flattened


def order_weekly_overview_columns(df, round_label):
    if df.empty:
        return df

    columns = list(df.columns)
    ordered = [column for column in ["Team Member"] if column in columns]

    if round_label:
        round_labels = [round_label]
    else:
        round_labels = sorted(
            {
                column.split(" / ")[0]
                for column in columns
                if column.startswith("Round ")
            },
            key=lambda label: int(label.split()[1]),
        )

    for current_round_label in round_labels:
        subtotal_columns = [
            f"{current_round_label} / Subtotal / Round Points",
            f"{current_round_label} / Subtotal / Round Rank",
            f"{current_round_label} / Subtotal / Round Tokens",
            f"{current_round_label} / Subtotal / Round Subtotal",
            f"{current_round_label} / Settlement / Pay To",
            f"{current_round_label} / Settlement / Pay Amount",
        ]
        gameweek_columns = [
            column for column in columns
            if column.startswith(f"{current_round_label} / GW ")
        ]
        gameweek_columns.sort(
            key=lambda column: (
                int(column.split(" / ")[1].split()[1]),
                {"Pts": 0, "Rank": 1, "Token": 2}.get(column.split(" / ")[-1], 3),
            )
        )
        ordered.extend(column for column in subtotal_columns if column in columns)
        ordered.extend(gameweek_columns)

    ordered.extend(
        column for column in [
            "Summary / Total Scores",
            "Summary / Total Prison Tokens",
        ]
        if column in columns
    )
    ordered.extend(column for column in columns if column not in ordered)
    return df[ordered]


def style_weekly_overview(dataframe):
    styles = pd.DataFrame("", index=dataframe.index, columns=dataframe.columns)
    light_yellow = "background-color: #fff2cc;"
    light_green = "background-color: #e2f0d9;"

    for column in dataframe.columns:
        if column.endswith((" / Round Points", " / Round Rank", " / Pts", " / Rank", " / Total Scores")):
            styles[column] = light_yellow
        elif column.endswith((" / Round Tokens", " / Token", " / Total Prison Tokens")):
            styles[column] = light_green

        if column.endswith(" / Round Subtotal"):
            styles[column] = light_green + "font-weight: bold;"

    return styles


def weekly_overview_column_config(dataframe):
    config = {
        "Team Member": st.column_config.TextColumn("Team Member", pinned=True),
    }
    for column in dataframe.columns:
        if column.endswith((" / Round Points", " / Round Rank", " / Pts", " / Rank", " / Total Scores")):
            config[column] = st.column_config.NumberColumn(column, format="%d")
        elif column.endswith((" / Round Tokens", " / Round Subtotal", " / Token", " / Total Prison Tokens")):
            config[column] = st.column_config.NumberColumn(column, format="%.1f")
    return config


def render_weekly_overview_table(dataframe, round_label):
    """Render one round with explicit grouped HTML table headers."""
    if dataframe.empty:
        return

    columns = list(dataframe.columns)
    team_member_column = ('Summary', '', 'Team Member')
    summary_columns = [
        ('Summary', '', 'Total Scores'),
        ('Summary', '', 'Total Prison Tokens'),
    ]
    round_columns = [column for column in columns if column[0] == round_label]
    ordered_columns = [team_member_column]
    ordered_columns.extend(column for column in round_columns if column[1] == 'Subtotal')
    ordered_columns.extend(column for column in round_columns if column[1] == 'Settlement')
    ordered_columns.extend(
        column for column in round_columns if column[1] not in ('Subtotal', 'Settlement')
    )
    ordered_columns.extend(column for column in summary_columns if column in columns)

    display_groups = {
        column: (
            f'{round_label} / {column[1].replace(" ", "")}'
            if column[1].startswith('GW ')
            else column[1] or 'Summary'
        )
        for column in ordered_columns[1:]
    }
    group_columns = []
    for column in ordered_columns[1:]:
        group = display_groups[column]
        if not group_columns or group_columns[-1][0] != group:
            group_columns.append([group, 0])
        group_columns[-1][1] += 1

    html = [
        '<div class="weekly-overview-table-wrapper"><table class="weekly-overview-table">',
        '<thead>',
        f'<tr><th colspan="{len(ordered_columns)}">{escape(round_label)}</th></tr>',
        '<tr><th rowspan="2" class="team-member-header">Team Member</th>',
    ]
    for group, span in group_columns:
        html.append(f'<th colspan="{span}">{escape(group)}</th>')
    html.append('</tr><tr>')
    for column in ordered_columns[1:]:
        html.append(f'<th>{escape(column[2])}</th>')
    html.append('</tr></thead><tbody>')

    group_index = {group: index for index, (group, _) in enumerate(group_columns)}
    for _, row in dataframe.iterrows():
        html.append('<tr>')
        for column_index, column in enumerate(ordered_columns):
            value = row[column]
            if pd.isna(value):
                value = ''
            classes = ['team-member-cell'] if column_index == 0 else []
            if column_index > 0:
                classes.append(f'group-{group_index[display_groups[column]] % 2}')
            if column[2] in ('Round Subtotal', 'Total Prison Tokens'):
                classes.append('emphasis-cell')
            if column[2] in ('Pay To', 'Pay Amount'):
                classes.append('settlement-cell')
            class_attribute = f' class="{" ".join(classes)}"' if classes else ''
            display_value = escape(str(value))
            if column[2] in ('Pay To', 'Pay Amount'):
                display_value = display_value.replace('\n', '<br>').replace(', ', '<br>')
            html.append(f'<td{class_attribute}>{display_value}</td>')
        html.append('</tr>')
    html.append(
        '</tbody></table></div>'
        '<style>'
        '.weekly-overview-table-wrapper { overflow-x: auto; }'
        '.weekly-overview-table { border-collapse: collapse; width: 100%; min-width: 900px; }'
        '.weekly-overview-table th, .weekly-overview-table td { '
        'border: 1px solid #d9d9d9; padding: 0.35rem 0.55rem; text-align: right; white-space: nowrap; }'
        '.weekly-overview-table thead th { background: #1f4e78; color: white; font-weight: 700; text-align: center; }'
        '.weekly-overview-table thead tr:first-child th { font-size: 1.05rem; }'
        '.weekly-overview-table .team-member-header { position: sticky; left: 0; '
        'text-align: left; background: #1f4e78; color: white; z-index: 2; }'
        '.weekly-overview-table .team-member-cell { position: sticky; left: 0; '
        'text-align: left; background: #f2f2f2; z-index: 1; }'
        '.weekly-overview-table .group-0 { background: #fff2cc; }'
        '.weekly-overview-table .group-1 { background: #e2f0d9; }'
        '.weekly-overview-table .emphasis-cell { font-weight: 700; }'
        '.weekly-overview-table .settlement-cell { white-space: pre-line; }'
        '</style>'
    )
    st.html(''.join(html))


@st.cache_data(ttl=300)
def load_data(league_id, gw):
    return get_league_data(league_id, gw)

@st.cache_data(ttl=300)
def load_weekly_overview(league_id, cache_version):
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
    summary_df['Ranking'] = custom_rank(summary_df['Team GW Points'])
    summary_df = summary_df.sort_values(
        by=['Ranking', 'Team GW Points'], ascending=[True, False]
    ).reset_index(drop=True)

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
            weekly_overview_df = load_weekly_overview(league_id, cache_version=2)

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

        if selected_round == 0:
            export_df = weekly_overview_df
            display_df = flatten_weekly_overview_columns(display_df)
            latest_round_label = f"Round {latest_round}"
            subtotal_column = f"{latest_round_label} / Subtotal / Round Subtotal"
            if subtotal_column in display_df.columns:
                display_df = display_df.sort_values(
                    subtotal_column,
                    ascending=False,
                    kind="stable",
                )
            display_df = order_weekly_overview_columns(display_df, None)
            st.dataframe(
                display_df.style.apply(style_weekly_overview, axis=None),
                width="stretch",
                hide_index=True,
                column_config=weekly_overview_column_config(display_df),
            )
        else:
            subtotal_column = (selected_round_label, 'Subtotal', 'Round Subtotal')
            display_df = display_df.sort_values(
                subtotal_column,
                ascending=False,
                kind="stable",
            )
            export_df = display_df
            render_weekly_overview_table(display_df, selected_round_label)
        
        # Add export button for weekly overview
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("📥 Export as PNG", key="export_weekly_overview"):
                try:
                    # Create a temporary file for the PNG
                    with tempfile.TemporaryDirectory() as tmpdir:
                        output_path = os.path.join(tmpdir, "weekly_overview.png")
                        generated_path = dataframe_to_jpeg(
                            export_df,
                            output_path, 
                            title=f"Weekly Overview - Round {selected_round if selected_round != 0 else 'All'}"
                        )
                        
                        # Read the file and offer download
                        with open(generated_path, 'rb') as f:
                            file_data = f.read()
                            file_name = f"weekly_overview_round_{selected_round if selected_round != 0 else 'all'}"
                            
                            st.download_button(
                                label="⬇️ Download PNG",
                                data=file_data,
                                file_name=f"{file_name}.png",
                                mime="image/png"
                            )
                        st.success("✅ Weekly overview exported successfully as PNG!")
                except Exception as e:
                    st.error(f"❌ Error exporting weekly overview: {e}")
