import requests
import pandas as pd


PRISON_LEAGUE_ID = 185376
GLOBAL_LEAGUE_ID = 314


def get_league_name(league_id: int):
    headers = {'User-Agent': 'Mozilla/5.0'}
    league_url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/?page_standings=1"
    response = requests.get(league_url, headers=headers, timeout=10)
    if response.status_code != 200:
        return None

    league_data = response.json().get('league')
    if not isinstance(league_data, dict):
        return None

    return league_data.get('name')


def get_league_title(league_id: int, league_name: str | None = None) -> str:
    name = (league_name or get_league_name(league_id) or '').strip()
    if not name:
        return 'FPL League Dashboard'
    if 'FPL' in name:
        return name
    return f"{name} FPL 26/27"


def get_summary_columns(league_id: int, columns):
    summary_cols = list(columns)
    if league_id == PRISON_LEAGUE_ID and 'Prison token' not in summary_cols:
        insert_index = summary_cols.index('Transfers Made') if 'Transfers Made' in summary_cols else len(summary_cols)
        summary_cols.insert(insert_index, 'Prison token')
    elif league_id != PRISON_LEAGUE_ID and 'Prison token' in summary_cols:
        summary_cols.remove('Prison token')
    return summary_cols


def build_player_selection_summary(picks_by_manager, players_map, teams_map, positions_map):
    selection_counts = {}
    for picks in picks_by_manager:
        for pick in picks:
            player_id = pick.get('element')
            player = players_map.get(player_id)
            if not player:
                continue

            selection = selection_counts.setdefault(player_id, {
                'Player Name': player.get('web_name', ''),
                'Club': teams_map.get(player.get('team'), ''),
                'Position': positions_map.get(player.get('element_type'), ''),
                'No. of Selections': 0,
            })
            selection['No. of Selections'] += 1

    columns = ['Player Name', 'Club', 'Position', 'No. of Selections']
    return pd.DataFrame(selection_counts.values(), columns=columns).sort_values(
        ['No. of Selections', 'Player Name'],
        ascending=[False, True],
    ).reset_index(drop=True)


def get_global_top_player_selections(gameweek: int, manager_limit: int = 100):
    headers = {'User-Agent': 'Mozilla/5.0'}
    session = requests.Session()

    bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    bootstrap = session.get(bootstrap_url, headers=headers, timeout=10).json()
    players_map = {player['id']: player for player in bootstrap.get('elements', [])}
    teams_map = {team['id']: team['name'] for team in bootstrap.get('teams', [])}
    positions_map = {
        position['id']: position['singular_name_short']
        for position in bootstrap.get('element_types', [])
    }

    picks_by_manager = []
    page = 1
    while len(picks_by_manager) < manager_limit:
        standings_url = (
            f"https://fantasy.premierleague.com/api/leagues-classic/"
            f"{GLOBAL_LEAGUE_ID}/standings/?page_standings={page}"
        )
        standings_response = session.get(standings_url, headers=headers, timeout=10)
        standings = standings_response.json().get('standings', {})
        managers = standings.get('results', [])
        if not managers:
            break

        for manager in managers[:manager_limit - len(picks_by_manager)]:
            picks_url = (
                f"https://fantasy.premierleague.com/api/entry/{manager['entry']}"
                f"/event/{gameweek}/picks/"
            )
            picks_response = session.get(picks_url, headers=headers, timeout=10)
            if picks_response.status_code == 200:
                picks_by_manager.append(picks_response.json().get('picks', []))

        if not standings.get('has_next'):
            break
        page += 1

    return build_player_selection_summary(
        picks_by_manager,
        players_map,
        teams_map,
        positions_map,
    )


def build_weekly_scores_from_history(history_payload):
    if not isinstance(history_payload, dict):
        history_data = history_payload or []
    else:
        history_data = history_payload.get('current', []) or history_payload.get('history', []) or history_payload.get('past', [])

    scores_by_event = {}
    for entry in history_data:
        event_id = entry.get('event')
        if event_id is None:
            continue
        scores_by_event[int(event_id)] = float(entry.get('points', 0) or 0)
    return scores_by_event


def custom_rank(scores: pd.Series) -> pd.Series:
    """
    Calculate rank as: number of people with higher score + 1
    Teams with equal points get the same rank.
    
    Formula: rank = count(scores > x) + 1
    """
    return scores.apply(lambda x: sum(scores > x) + 1)


def calculate_weekly_prison_tokens(rankings: pd.Series) -> pd.Series:
    contribution_by_rank = {4: 20, 5: 20, 6: 30, 7: 30}
    token_values = -rankings.map(contribution_by_rank).fillna(0)
    token_pool = -token_values.sum()

    rank_one = rankings == 1
    rank_two = rankings == 2
    if rank_one.any():
        token_values.loc[rank_one] = token_pool * 0.7 / rank_one.sum()
    if rank_two.any():
        token_values.loc[rank_two] = token_pool * 0.3 / rank_two.sum()

    return token_values.round(2)


def calculate_round_prison_tokens(round_points: pd.Series) -> pd.Series:
    ranking = custom_rank(round_points)
    contributions = pd.Series(0.0, index=round_points.index)

    for manager_name, rank in ranking.items():
        if rank in (4, 5):
            contributions[manager_name] = 50
        elif rank in (6, 7):
            contributions[manager_name] = 100
        else:
            contributions[manager_name] = 0

    pool = contributions.sum()
    result = pd.Series(0.0, index=round_points.index)

    rank_one = ranking == 1
    rank_two = ranking == 2
    if rank_one.any():
        result.loc[rank_one] = pool * 0.7 / rank_one.sum()
    if rank_two.any():
        result.loc[rank_two] = pool * 0.3 / rank_two.sum()

    return result.round(2)


def calculate_live_team_points(picks, live_points):
    total = 0
    for pick in picks or []:
        multiplier = pick.get('multiplier', 1)
        if multiplier == 0:
            continue
        total += live_points.get(pick.get('element'), 0) * int(multiplier)
    return total


def build_player_selection_summary(picks, players, teams, positions):
    selection_counts = {}

    for manager_picks in picks or []:
        for pick in manager_picks or []:
            element_id = pick.get('element')
            if element_id is None:
                continue

            player = players.get(element_id, {})
            player_name = player.get('web_name') or f"Player {element_id}"
            club_name = teams.get(player.get('team'), '')
            position_name = positions.get(player.get('element_type'), '')

            key = (player_name, club_name, position_name)
            if key not in selection_counts:
                selection_counts[key] = {
                    'Player Name': player_name,
                    'Club': club_name,
                    'Position': position_name,
                    'No. of Selections': 0,
                }
            selection_counts[key]['No. of Selections'] += 1

    df = pd.DataFrame(list(selection_counts.values()))
    if df.empty:
        return pd.DataFrame(columns=['Player Name', 'Club', 'Position', 'No. of Selections'])

    return df.sort_values(['No. of Selections', 'Player Name'], ascending=[False, True]).reset_index(drop=True)


def get_global_top_player_selections(gameweek: int):
    headers = {'User-Agent': 'Mozilla/5.0'}
    bootstrap_url = 'https://fantasy.premierleague.com/api/bootstrap-static/'
    try:
        bootstrap = requests.get(bootstrap_url, headers=headers, timeout=10).json()
    except requests.RequestException:
        return pd.DataFrame(columns=['Player Name', 'Club', 'Position', 'No. of Selections'])

    players = {player['id']: player for player in bootstrap.get('elements', [])}
    teams = {team['id']: team['name'] for team in bootstrap.get('teams', [])}
    positions = {pos['id']: pos['singular_name_short'] for pos in bootstrap.get('element_types', [])}

    return build_player_selection_summary([], players, teams, positions)


def get_gameweek_data_status(events, gameweek: int):
    event = next((event for event in events if event.get('id') == gameweek), None)
    if event is None:
        return 'upcoming'
    if event.get('finished'):
        return 'confirmed'
    if event.get('is_current'):
        return 'live'
    if event.get('is_next') or gameweek > max((e.get('id', 0) for e in events), default=0):
        return 'upcoming'
    return 'upcoming'


def get_latest_gameweek():
    headers = {'User-Agent': 'Mozilla/5.0'}
    bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    bootstrap = requests.get(bootstrap_url, headers=headers).json()

    in_progress = [event['id'] for event in bootstrap.get('events', []) if event.get('is_current')]
    if in_progress:
        return max(in_progress)

    finished = [event['id'] for event in bootstrap.get('events', []) if event.get('finished')]
    if finished:
        return max(finished)

    return 1


def get_weekly_overview(league_id: int):
    headers = {'User-Agent': 'Mozilla/5.0'}
    session = requests.Session()
    bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    bootstrap = session.get(bootstrap_url, headers=headers, timeout=10).json()
    current_event = next((event for event in bootstrap.get('events', []) if event.get('is_current')), None)
    current_live_week = current_event.get('id') if current_event else 0
    latest_confirmed_week = max(
        (event['id'] for event in bootstrap['events'] if event['finished']),
        default=0,
    )

    managers = []
    page = 1
    has_next = True
    while has_next:
        league_url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/?page_standings={page}"
        standings = session.get(league_url, headers=headers, timeout=10).json().get(
            'standings', {}
        )
        managers.extend(
            (manager['entry'], manager['player_name'])
            for manager in standings.get('results', [])
        )
        has_next = standings.get('has_next', False)
        page += 1

    round_groups = {
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

    weekly_scores = {manager_name: [0] * 38 for _, manager_name in managers}
    weekly_tokens = {manager_name: [0] * 38 for _, manager_name in managers}
    weekly_ranks = {}
    history_by_manager = {}

    for entry_id, manager_name in managers:
        history_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
        history_response = session.get(history_url, headers=headers, timeout=10)
        if history_response.status_code == 200:
            payload = history_response.json()
            history_by_manager[manager_name] = build_weekly_scores_from_history(payload)
        else:
            history_by_manager[manager_name] = {}

        if current_live_week > 0:
            picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{current_live_week}/picks/"
            picks_response = session.get(picks_url, headers=headers, timeout=10)
            if picks_response.status_code == 200:
                picks_data = picks_response.json()
                live_url = f"https://fantasy.premierleague.com/api/event/{current_live_week}/live/"
                live_response = session.get(live_url, headers=headers, timeout=10)
                if live_response.status_code == 200:
                    live_points = {
                        el['id']: el['stats']['total_points']
                        for el in live_response.json().get('elements', [])
                    }
                    live_score = calculate_live_team_points(
                        picks_data.get('picks', []),
                        live_points,
                    )
                    history_by_manager[manager_name][current_live_week] = float(live_score)

    for week in range(1, 39):
        week_scores = {
            manager_name: history_by_manager.get(manager_name, {}).get(week, 0)
            for _, manager_name in managers
        }

        has_confirmed_data = week <= latest_confirmed_week
        has_live_data = week == current_live_week and current_live_week > 0

        if has_confirmed_data or has_live_data:
            score_series = pd.Series(week_scores, dtype='float64')
            rankings = custom_rank(score_series)
            contributions = calculate_weekly_prison_tokens(rankings)
        else:
            rankings = pd.Series({manager_name: 0 for _, manager_name in managers}, dtype='int64')
            contributions = pd.Series({manager_name: 0 for _, manager_name in managers}, dtype='float64')

        weekly_ranks[week] = rankings.to_dict()
        for _, manager_name in managers:
            score = week_scores.get(manager_name, 0)
            token = round(float(contributions.get(manager_name, 0)), 2)
            weekly_scores[manager_name][week - 1] = score
            weekly_tokens[manager_name][week - 1] = token

    rows = []
    columns = [
        ('Summary', '', 'Team Member'),
        ('Summary', '', 'Total Scores'),
        ('Summary', '', 'Total Prison Tokens'),
    ]
    for round_no, round_weeks in round_groups.items():
        round_label = f'Round {round_no}'
        for week in round_weeks:
            columns.append((round_label, f'GW {week}', 'Pts'))
            columns.append((round_label, f'GW {week}', 'Rank'))
            columns.append((round_label, f'GW {week}', 'Token'))
        columns.append((round_label, 'Subtotal', 'Round Points'))
        columns.append((round_label, 'Subtotal', 'Round Rank'))
        columns.append((round_label, 'Subtotal', 'Round Tokens'))
        columns.append((round_label, 'Subtotal', 'Round Subtotal'))

    for _, manager_name in managers:
        row = {
            ('Summary', '', 'Team Member'): manager_name,
            ('Summary', '', 'Total Scores'): sum(weekly_scores[manager_name]),
        }

        gw_token_total = float(sum(weekly_tokens[manager_name]))
        round_tokens_total = 0.0
        for round_no, round_weeks in round_groups.items():
            round_label = f'Round {round_no}'
            round_points = 0
            round_token_total = 0.0
            for week in round_weeks:
                points = weekly_scores[manager_name][week - 1]
                rank = weekly_ranks.get(week, {}).get(manager_name, 0)
                token = weekly_tokens[manager_name][week - 1]
                row[(round_label, f'GW {week}', 'Pts')] = points
                row[(round_label, f'GW {week}', 'Rank')] = rank
                row[(round_label, f'GW {week}', 'Token')] = token
                round_points += points
                round_token_total += token

            round_points_by_manager = {}
            for _, other_name in managers:
                round_points_by_manager[other_name] = sum(
                    weekly_scores[other_name][week - 1]
                    for week in round_weeks
                    if week <= latest_confirmed_week or week == current_live_week
                )
            round_rank_series = pd.Series(round_points_by_manager, dtype='float64')
            round_rank = custom_rank(round_rank_series).get(manager_name, 0)

            round_token_pool_values = {}
            for _, other_name in managers:
                round_token_pool_values[other_name] = sum(
                    weekly_tokens[other_name][week - 1]
                    for week in round_weeks
                    if week <= latest_confirmed_week or week == current_live_week
                )
            round_token_series = pd.Series(round_token_pool_values, dtype='float64')
            round_token_rank = custom_rank(round_token_series)
            round_contributions = -round_token_rank.map({4: 50, 5: 50, 6: 100, 7: 100}).fillna(0)
            round_pool = -round_contributions.sum()
            round_first = round_token_rank == 1
            round_second = round_token_rank == 2
            if round_first.any():
                round_contributions.loc[round_first] = round_pool * 0.7 / round_first.sum()
            if round_second.any():
                round_contributions.loc[round_second] = round_pool * 0.3 / round_second.sum()

            round_tokens_for_manager = round_contributions.get(manager_name, 0.0)
            round_tokens_total += round_tokens_for_manager
            round_subtotal = round_token_total + round_tokens_for_manager

            row[(round_label, 'Subtotal', 'Round Points')] = round_points
            row[(round_label, 'Subtotal', 'Round Rank')] = int(round_rank)
            row[(round_label, 'Subtotal', 'Round Tokens')] = round(round_tokens_for_manager, 2)
            row[(round_label, 'Subtotal', 'Round Subtotal')] = round(round_subtotal, 2)

        row[('Summary', '', 'Total Prison Tokens')] = round(gw_token_total + round_tokens_total, 2)
        rows.append(row)

    df = pd.DataFrame(rows, columns=pd.MultiIndex.from_tuples(columns))
    return df

def get_league_data(league_id: int, gameweek: int):
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 1. Fetch static data (players, clubs, positions)
    bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    bootstrap = requests.get(bootstrap_url, headers=headers).json()
    
    players_map = {p['id']: p for p in bootstrap['elements']}
    teams_map = {t['id']: t['name'] for t in bootstrap['teams']}
    positions_map = {pos['id']: pos['singular_name_short'] for pos in bootstrap['element_types']}
    selected_event = next(
        (event for event in bootstrap['events'] if event['id'] == gameweek),
        None,
    )
    if selected_event is None:
        gameweek_status = 'Upcoming'
    else:
        data_status = get_gameweek_data_status(bootstrap['events'], gameweek)
        if data_status == 'confirmed':
            gameweek_status = 'Finished'
        elif data_status == 'live':
            gameweek_status = 'In Progress'
        elif data_status == 'upcoming':
            gameweek_status = 'Upcoming'
        else:
            gameweek_status = 'Scheduled'
    
    # 2. Fetch Gameweek Fixtures data
    fixtures_url = f"https://fantasy.premierleague.com/api/fixtures/?event={gameweek}"
    fixtures_data = requests.get(fixtures_url, headers=headers).json()
    
    club_fixtures = {team_id: [] for team_id in teams_map.keys()}
    for f in fixtures_data:
        home_id, away_id = f['team_h'], f['team_a']
        club_fixtures[home_id].append({
            'opponent': f"{teams_map.get(away_id)} (H)",
            'difficulty': f['team_h_difficulty']
        })
        club_fixtures[away_id].append({
            'opponent': f"{teams_map.get(home_id)} (A)",
            'difficulty': f['team_a_difficulty']
        })
        
    # 3. Fetch Gameweek Live Points for all players
    live_url = f"https://fantasy.premierleague.com/api/event/{gameweek}/live/"
    live_data = requests.get(live_url, headers=headers).json()
    live_points = {el['id']: el['stats']['total_points'] for el in live_data['elements']}
    
    # 4. Fetch all managers in the league
    managers = []
    page = 1
    has_next = True
    
    while has_next:
        league_url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/?page_standings={page}"
        league_resp = requests.get(league_url, headers=headers).json()
        
        standings = league_resp.get('standings', {})
        for mgr in standings.get('results', []):
            managers.append({
                'entry_id': mgr['entry'],
                'team_name': mgr['entry_name'],
                'manager_name': mgr['player_name']
            })
            
        has_next = standings.get('has_next', False)
        page += 1

    # 5. Compile data for every manager
    all_rows = []
    for mgr in managers:
        entry_id = mgr['entry_id']
        picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{gameweek}/picks/"
        picks_resp = requests.get(picks_url, headers=headers)
        
        if picks_resp.status_code != 200:
            continue
            
        picks_data = picks_resp.json()
        
        entry_history = picks_data.get('entry_history', {})
        data_status = get_gameweek_data_status(bootstrap['events'], gameweek)
        if data_status == 'live':
            team_gw_points = calculate_live_team_points(picks_data.get('picks', []), live_points)
        else:
            team_gw_points = entry_history.get('points', 0)
        transfers_made = entry_history.get('event_transfers', 0)

        active_chip = picks_data.get('active_chip')
        card_used = active_chip.replace('_', ' ').title() if active_chip else "None"

        for pick in picks_data.get('picks', []):
            p_id = pick['element']
            player = players_map.get(p_id, {})
            club_id = player.get('team')
            
            p_fixtures = club_fixtures.get(club_id, [])
            if not p_fixtures:
                opponents = "Blank"
                difficulty = "N/A"
            else:
                opponents = ", ".join([fix['opponent'] for fix in p_fixtures])
                difficulty = ", ".join([str(fix['difficulty']) for fix in p_fixtures])
            
            is_substitute = pick.get('position', 0) > 11
            
            if pick.get('is_captain'):
                cap_status = 'Captain'
            elif pick.get('is_vice_captain'):
                cap_status = 'Vice Captain'
            else:
                cap_status = 'None'
                
            all_rows.append({
                "Gameweek": gameweek,
                "Gameweek Status": gameweek_status,
                "Manager Name": mgr['manager_name'],
                "Team Name": mgr['team_name'],
                "Team GW Points": team_gw_points,
                "Transfers Made": transfers_made,
                "Player": player.get('web_name'),
                "Position": positions_map.get(player.get('element_type')),
                "Club": teams_map.get(club_id),
                "Opponent": opponents,
                "Opponent Difficulty": difficulty,
                "Player Points": live_points.get(p_id, 0),
                "Is Substitute": is_substitute,
                "Card Used": card_used,
                "Captain Status": cap_status
            })

    return pd.DataFrame(all_rows)


def dataframe_to_png(df, output_path, title="Weekly Overview"):
    """
    Convert a pandas DataFrame to a PNG image using matplotlib.
    Reorders columns and wraps header text for better readability.
    
    Args:
        df: pandas DataFrame to convert
        output_path: path where the PNG will be saved (should end with .png)
        title: title for the table
    
    Returns:
        path to the generated PNG file
    """
    import matplotlib.pyplot as plt
    from textwrap import wrap
    
    try:
        df_display = df.copy()
        is_grouped = isinstance(df_display.columns, pd.MultiIndex) and df_display.columns.nlevels == 3
        if is_grouped:
            columns = list(df_display.columns)
            team_member = ('Summary', '', 'Team Member')
            ordered_columns = [team_member] if team_member in columns else []
            for round_name in dict.fromkeys(column[0] for column in columns if column[0] != 'Summary'):
                round_columns = [column for column in columns if column[0] == round_name]
                ordered_columns.extend(column for column in round_columns if column[1] == 'Subtotal')
                ordered_columns.extend(column for column in round_columns if column[1].startswith('GW '))
            ordered_columns.extend(column for column in columns if column[0] == 'Summary' and column not in ordered_columns)
            ordered_columns.extend(column for column in columns if column not in ordered_columns)
            df_display = df_display[ordered_columns]
            table_headers = [
                ["" for _ in ordered_columns],
                ["" for _ in ordered_columns],
                [str(column[2]) for column in ordered_columns],
            ]
            if ordered_columns:
                table_headers[0][0] = "Round 1"
                table_headers[1][0] = "Team Member"
            for index, column in enumerate(ordered_columns[1:], start=1):
                table_headers[1][index] = (
                    f'{column[0]} / {column[1].replace(" ", "")}'
                    if column[1].startswith('GW ')
                    else column[1] or 'Summary'
                )
            if ordered_columns:
                table_headers[1][-1] = table_headers[1][-1] or 'Summary'
        else:
            table_headers = [[str(column) for column in df_display.columns]]
        
        # Ensure the output path ends with .png
        if not output_path.endswith('.png'):
            output_path = output_path.replace('.jpeg', '.png').replace('.html', '.png')
            if not output_path.endswith('.png'):
                output_path = output_path + '.png'
        
        # Create figure and axis with more space for the grouped headers.
        header_rows = len(table_headers)
        fig, ax = plt.subplots(figsize=(20, max(10, len(df_display) * 0.45)))
        ax.axis('tight')
        ax.axis('off')
        
        table_data = []
        for header_row in table_headers:
            table_data.append(['\n'.join(wrap(header, width=14)) for header in header_row])
        
        for _, row in df_display.iterrows():
            table_data.append(row.tolist())
        
        # Calculate column widths - make first column wider for Team Member
        col_widths = [0.10] + [0.06] * (len(df_display.columns) - 1)
        
        table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                        colWidths=col_widths)
        
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 1.8 if header_rows == 1 else 1.35)
        
        # Style header row with text wrapping
        for row_index in range(header_rows):
            for column_index in range(len(df_display.columns)):
                cell = table[(row_index, column_index)]
                cell.set_facecolor('#4472C4')
                cell.set_text_props(weight='bold', color='white', ha='center', va='center')
                cell.set_height(0.06 if header_rows == 1 else 0.045)

        if is_grouped:
            for column_index in range(1, len(df_display.columns)):
                table[(0, column_index)].visible_edges = 'BT'
                table[(1, column_index)].visible_edges = 'BT'
            table[(1, 0)].visible_edges = 'LRT'
            table[(2, 0)].visible_edges = 'LRB'
        
        # Style data rows with alternating colors
        for i in range(header_rows, len(table_data)):
            for j in range(len(df_display.columns)):
                cell = table[(i, j)]
                if j == 0:
                    cell.set_facecolor('#F2F2F2')
                elif (j - 1) % 2 == 0:
                    cell.set_facecolor('#FFF2CC')
                else:
                    cell.set_facecolor('#E2F0D9')
                cell.set_text_props(ha='center', va='center')
        
        # Add title
        plt.title(title, fontsize=14, fontweight='bold', pad=20)
        
        # Save to file
        plt.savefig(output_path, bbox_inches='tight', dpi=100, facecolor='white')
        plt.close(fig)
        
        return output_path
        
    except Exception as e:
        print(f"Error in dataframe_to_png: {e}")
        raise


def dataframe_to_jpeg(df, output_path, title="Weekly Overview"):
    """
    Legacy function for backward compatibility. 
    Converts DataFrame to PNG instead (user prefers PNG format).
    
    Args:
        df: pandas DataFrame to convert
        output_path: path where the image will be saved
        title: title for the table
    
    Returns:
        path to the generated PNG file
    """
    return dataframe_to_png(df, output_path, title)


def send_email_with_attachment(recipient_email, subject, body, attachment_path=None, sender_email=None, sender_password=None):
    """
    Send an email with optional attachment.
    
    Args:
        recipient_email: email address to send to
        subject: email subject
        body: email body text
        attachment_path: path to file to attach (optional)
        sender_email: sender's email address
        sender_password: sender's email password
    
    Returns:
        True if successful, False otherwise
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    import os
    
    if not sender_email or not sender_password:
        print("Error: Email sender credentials not provided")
        return False
    
    try:
        # Create the email message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject
        
        # Add body
        msg.attach(MIMEText(body, 'plain'))
        
        # Add attachment if provided
        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, 'rb') as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename= {os.path.basename(attachment_path)}')
                    msg.attach(part)
            except Exception as e:
                print(f"Error attaching file: {e}")
                return False
        
        # Send the email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        print(f"Email sent successfully to {recipient_email}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
