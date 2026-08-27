import requests
import pandas as pd

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

    weekly_scores = {
        manager_name: [0] * 38 for _, manager_name in managers
    }
    weekly_tokens = {
        manager_name: [0] * 38 for _, manager_name in managers
    }
    for week in range(1, latest_confirmed_week + 1):
        week_scores = {}
        for entry_id, manager_name in managers:
            picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{week}/picks/"
            picks_response = requests.get(picks_url, headers=headers)
            if picks_response.status_code == 200:
                week_scores[manager_name] = picks_response.json().get(
                    'entry_history', {}
                ).get('points', 0)
            else:
                week_scores[manager_name] = 0

        score_series = pd.Series(week_scores, dtype='float64')
        rankings = score_series.rank(method='dense', ascending=False).astype(int)
        contributions = -rankings.map({4: 20, 5: 20, 6: 30, 7: 30}).fillna(0)
        token_pool = -contributions.sum()
        first_place = rankings == 1
        second_place = rankings == 2
        if first_place.any():
            contributions.loc[first_place] = token_pool * 0.7 / first_place.sum()
        if second_place.any():
            contributions.loc[second_place] = token_pool * 0.3 / second_place.sum()

        for manager_name, score in week_scores.items():
            weekly_scores[manager_name][week - 1] = score
            weekly_tokens[manager_name][week - 1] = round(
                contributions.get(manager_name, 0), 2
            )

    overview = []
    for _, manager_name in managers:
        row = {
            'Team Member': manager_name,
            'Total Scores': sum(weekly_scores[manager_name]),
            'Total Prison Tokens': round(sum(weekly_tokens[manager_name]), 2),
        }
        row.update({
            f'GW {week}': weekly_scores[manager_name][week - 1]
            for week in range(1, 39)
        })
        overview.append(row)

    return pd.DataFrame(overview, columns=[
        'Team Member', 'Total Scores', 'Total Prison Tokens',
        *[f'GW {week}' for week in range(1, 39)],
    ])

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
