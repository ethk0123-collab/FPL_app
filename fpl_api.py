import requests
import pandas as pd


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
    ranking = round_points.rank(method='dense', ascending=False).astype(int)
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
    bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    bootstrap = requests.get(bootstrap_url, headers=headers).json()
    latest_confirmed_week = max(
        (event['id'] for event in bootstrap['events'] if event['finished']),
        default=0,
    )

    managers = []
    page = 1
    has_next = True
    while has_next:
        league_url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/?page_standings={page}"
        standings = requests.get(league_url, headers=headers).json().get(
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

    for week in range(1, 39):
        week_scores = {}
        for entry_id, manager_name in managers:
            picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{week}/picks/"
            picks_response = requests.get(picks_url, headers=headers)
            if picks_response.status_code == 200:
                week_scores[manager_name] = picks_response.json().get('entry_history', {}).get('points', 0)
            else:
                week_scores[manager_name] = 0

        if week <= latest_confirmed_week:
            score_series = pd.Series(week_scores, dtype='float64')
            rankings = score_series.rank(method='dense', ascending=False).astype(int)
            contributions = calculate_weekly_prison_tokens(rankings)
        else:
            rankings = pd.Series({manager_name: 0 for _, manager_name in managers}, dtype='int64')
            contributions = pd.Series({manager_name: 0 for _, manager_name in managers}, dtype='float64')

        weekly_ranks[week] = rankings.to_dict()
        for manager_name, score in week_scores.items():
            weekly_scores[manager_name][week - 1] = score
            weekly_tokens[manager_name][week - 1] = round(float(contributions.get(manager_name, 0)), 2)

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
                    weekly_scores[other_name][week - 1] for week in round_weeks if week <= latest_confirmed_week
                )
            round_rank_series = pd.Series(round_points_by_manager, dtype='float64')
            round_rank = round_rank_series.rank(method='dense', ascending=False).astype(int).get(manager_name, 0)

            round_token_pool_values = {}
            for _, other_name in managers:
                round_token_pool_values[other_name] = sum(
                    weekly_tokens[other_name][week - 1] for week in round_weeks if week <= latest_confirmed_week
                )
            round_token_series = pd.Series(round_token_pool_values, dtype='float64')
            round_token_rank = round_token_series.rank(method='dense', ascending=False).astype(int)
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
        event for event in bootstrap['events'] if event['id'] == gameweek
    )
    if selected_event['finished']:
        gameweek_status = 'Finished'
    elif selected_event['is_current']:
        gameweek_status = 'In Progress'
    elif selected_event['is_next']:
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
