import requests
import pandas as pd


PRISON_LEAGUE_ID = 185376
GLOBAL_LEAGUE_ID = 314


def calculate_waterfall_settlements(round_subtotals):
    """Return sequential payment instructions for one round's balances."""
    ordered_balances = sorted(round_subtotals.items(), key=lambda item: item[1], reverse=True)
    remaining_receivers = [
        [manager_name, round(float(balance), 2)]
        for manager_name, balance in ordered_balances
        if balance > 0
    ]
    settlements = {manager_name: ("-", "-") for manager_name in round_subtotals}
    receiver_index = 0

    for manager_name, balance in ordered_balances:
        if balance >= 0:
            continue

        remaining_debt = round(-float(balance), 2)
        payees = []
        amounts = []
        while remaining_debt > 0 and receiver_index < len(remaining_receivers):
            receiver_name, receiver_balance = remaining_receivers[receiver_index]
            payment = round(min(remaining_debt, receiver_balance), 2)
            if payment > 0:
                payees.append(receiver_name)
                amounts.append(payment)
                remaining_debt = round(remaining_debt - payment, 2)
                remaining_receivers[receiver_index][1] = round(receiver_balance - payment, 2)

            if remaining_receivers[receiver_index][1] == 0:
                receiver_index += 1

        settlements[manager_name] = (
            "\n".join(payees) or "-",
            "\n".join(f"{amount:.2f}" for amount in amounts) or "-",
        )

    return settlements


def is_round_settlement_available(round_weeks, latest_confirmed_week):
    return bool(round_weeks) and round_weeks[-1] <= latest_confirmed_week


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


def fetch_all_players():
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

    return players_map, teams_map, positions_map, session, headers


def fetch_top_manager_picks(gameweek: int, manager_limit: int = 100):
    players_map, teams_map, positions_map, session, headers = fetch_all_players()

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

    return picks_by_manager, players_map, teams_map, positions_map, session, headers


def get_global_top_player_selections(gameweek: int, manager_limit: int = 100):
    picks_by_manager, players_map, teams_map, positions_map, _, _ = fetch_top_manager_picks(
        gameweek, manager_limit
    )
    return build_player_selection_summary(
        picks_by_manager,
        players_map,
        teams_map,
        positions_map,
    )


def build_player_weekly_points_matrix(player_ids, players_map, teams_map, positions_map, session, headers, total_gameweeks=38):
    columns = ['Player Name', 'Club', 'Position', 'Total Points', 'Average Points'] + [
        f'GW{gw}' for gw in range(1, total_gameweeks + 1)
    ]
    rows = []
    for player_id in player_ids:
        player = players_map.get(player_id)
        if not player:
            continue

        points_by_week = {}
        matches_played = 0
        try:
            summary_url = f"https://fantasy.premierleague.com/api/element-summary/{player_id}/"
            summary = session.get(summary_url, headers=headers, timeout=10).json()
            for gw_entry in summary.get('history', []):
                round_no = gw_entry.get('round')
                if round_no is not None:
                    points_by_week[int(round_no)] = gw_entry.get('total_points', 0)
                    if gw_entry.get('minutes', 0) > 0:
                        matches_played += 1
        except requests.RequestException:
            pass

        total_points = sum(points_by_week.values())
        row = {
            'Player Name': player.get('web_name', ''),
            'Club': teams_map.get(player.get('team'), ''),
            'Position': positions_map.get(player.get('element_type'), ''),
            'Total Points': total_points,
            'Average Points': round(total_points / matches_played, 2) if matches_played > 0 else 0,
        }
        for gw in range(1, total_gameweeks + 1):
            row[f'GW{gw}'] = points_by_week.get(gw, 0)
        rows.append(row)

    return pd.DataFrame(rows, columns=columns)



def get_global_top_player_weekly_points(gameweek: int, manager_limit: int = 100, total_gameweeks: int = 38):
    players_map, teams_map, positions_map, session, headers = fetch_all_players()
    player_ids = sorted(players_map.keys())
    return build_player_weekly_points_matrix(
        player_ids, players_map, teams_map, positions_map, session, headers, total_gameweeks
    )


def build_player_points_by_difficulty_matrix(player_ids, players_map, teams_map, positions_map, session, headers):
    """Build a matrix of total/average points split by fixture difficulty rating (1-5) for each player."""
    difficulty_levels = [1, 2, 3, 4, 5]
    columns = ['Player Name', 'Club', 'Position', 'Total Points', 'Average Points']
    for level in difficulty_levels:
        columns += [f'Total Pts (FDR {level})', f'Avg Pts (FDR {level})']

    try:
        fixtures = requests.get(
            'https://fantasy.premierleague.com/api/fixtures/', headers=headers, timeout=10
        ).json()
    except requests.RequestException:
        fixtures = []
    fixtures_by_id = {fixture['id']: fixture for fixture in fixtures if fixture.get('id') is not None}

    rows = []
    for player_id in player_ids:
        player = players_map.get(player_id)
        if not player:
            continue

        total_points = 0
        matches_played = 0
        points_by_difficulty = {level: 0 for level in difficulty_levels}
        matches_by_difficulty = {level: 0 for level in difficulty_levels}
        try:
            summary_url = f"https://fantasy.premierleague.com/api/element-summary/{player_id}/"
            summary = session.get(summary_url, headers=headers, timeout=10).json()
            for gw_entry in summary.get('history', []):
                points = gw_entry.get('total_points', 0)
                minutes = gw_entry.get('minutes', 0)
                total_points += points
                if minutes > 0:
                    matches_played += 1

                fixture = fixtures_by_id.get(gw_entry.get('fixture'))
                if not fixture:
                    continue
                difficulty = (
                    fixture.get('team_h_difficulty')
                    if gw_entry.get('was_home')
                    else fixture.get('team_a_difficulty')
                )
                if difficulty in points_by_difficulty:
                    points_by_difficulty[difficulty] += points
                    if minutes > 0:
                        matches_by_difficulty[difficulty] += 1
        except requests.RequestException:
            pass

        row = {
            'Player Name': player.get('web_name', ''),
            'Club': teams_map.get(player.get('team'), ''),
            'Position': positions_map.get(player.get('element_type'), ''),
            'Total Points': total_points,
            'Average Points': round(total_points / matches_played, 2) if matches_played > 0 else 0,
        }
        for level in difficulty_levels:
            level_matches = matches_by_difficulty[level]
            row[f'Total Pts (FDR {level})'] = points_by_difficulty[level]
            row[f'Avg Pts (FDR {level})'] = round(points_by_difficulty[level] / level_matches, 2) if level_matches > 0 else 0
        rows.append(row)

    return pd.DataFrame(rows, columns=columns)


def get_global_top_player_points_by_difficulty(gameweek: int, manager_limit: int = 100):
    players_map, teams_map, positions_map, session, headers = fetch_all_players()
    player_ids = sorted(players_map.keys())
    return build_player_points_by_difficulty_matrix(
        player_ids, players_map, teams_map, positions_map, session, headers
    )


def build_player_minutes_played_matrix(player_ids, players_map, teams_map, positions_map, session, headers, total_gameweeks=38):
    columns = ['Player Name', 'Club', 'Position', 'Total Minutes', '# of Match >0 min'] + [
        f'Wk{gw}' for gw in range(1, total_gameweeks + 1)
    ]
    rows = []
    for player_id in player_ids:
        player = players_map.get(player_id)
        if not player:
            continue

        minutes_by_week = {}
        try:
            summary_url = f"https://fantasy.premierleague.com/api/element-summary/{player_id}/"
            summary = session.get(summary_url, headers=headers, timeout=10).json()
            for gw_entry in summary.get('history', []):
                round_no = gw_entry.get('round')
                if round_no is not None:
                    minutes_by_week[int(round_no)] = gw_entry.get('minutes', 0)
        except requests.RequestException:
            pass

        row = {
            'Player Name': player.get('web_name', ''),
            'Club': teams_map.get(player.get('team'), ''),
            'Position': positions_map.get(player.get('element_type'), ''),
            'Total Minutes': sum(minutes_by_week.values()),
            '# of Match >0 min': sum(1 for minutes in minutes_by_week.values() if minutes > 0),
        }
        for gw in range(1, total_gameweeks + 1):
            row[f'Wk{gw}'] = minutes_by_week.get(gw, 0)
        rows.append(row)

    return pd.DataFrame(rows, columns=columns)


def get_global_top_player_minutes_played(gameweek: int, manager_limit: int = 100, total_gameweeks: int = 38):
    players_map, teams_map, positions_map, session, headers = fetch_all_players()
    player_ids = sorted(players_map.keys())
    return build_player_minutes_played_matrix(
        player_ids, players_map, teams_map, positions_map, session, headers, total_gameweeks
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


def get_team_fixture_difficulty_matrix(total_gameweeks: int = 38):
    """Build a Club x Gameweek fixture difficulty matrix using the FPL fixtures API."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    empty_columns = ['Club'] + [f'GW{gw}' for gw in range(1, total_gameweeks + 1)]
    try:
        bootstrap = requests.get(
            'https://fantasy.premierleague.com/api/bootstrap-static/', headers=headers, timeout=10
        ).json()
        fixtures = requests.get(
            'https://fantasy.premierleague.com/api/fixtures/', headers=headers, timeout=10
        ).json()
    except requests.RequestException:
        empty_df = pd.DataFrame(columns=empty_columns)
        return empty_df, empty_df.copy()

    teams = {team['id']: team for team in bootstrap.get('teams', [])}
    team_ids = sorted(teams.keys(), key=lambda tid: teams[tid]['name'])

    opponents_by_team = {tid: {} for tid in team_ids}
    difficulty_by_team = {tid: {} for tid in team_ids}

    for fixture in fixtures:
        event = fixture.get('event')
        home_id = fixture.get('team_h')
        away_id = fixture.get('team_a')
        if event is None or home_id not in teams or away_id not in teams:
            continue

        home_short = teams[away_id]['short_name']
        away_short = teams[home_id]['short_name']

        opponents_by_team[home_id].setdefault(event, []).append(f"{home_short} (H)")
        difficulty_by_team[home_id].setdefault(event, []).append(fixture.get('team_h_difficulty', 0))

        opponents_by_team[away_id].setdefault(event, []).append(f"{away_short} (A)")
        difficulty_by_team[away_id].setdefault(event, []).append(fixture.get('team_a_difficulty', 0))

    display_rows = []
    difficulty_rows = []
    for tid in team_ids:
        display_row = {'Club': teams[tid]['name']}
        difficulty_row = {'Club': teams[tid]['name']}
        for gw in range(1, total_gameweeks + 1):
            opponents = opponents_by_team[tid].get(gw, [])
            difficulties = difficulty_by_team[tid].get(gw, [])
            display_row[f'GW{gw}'] = ' / '.join(opponents) if opponents else '-'
            difficulty_row[f'GW{gw}'] = max(difficulties) if difficulties else 0
        display_rows.append(display_row)
        difficulty_rows.append(difficulty_row)

    return pd.DataFrame(display_rows, columns=empty_columns), pd.DataFrame(difficulty_rows, columns=empty_columns)


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
        if is_round_settlement_available(round_weeks, latest_confirmed_week):
            columns.append((round_label, 'Settlement', 'Pay To'))
            columns.append((round_label, 'Settlement', 'Pay Amount'))

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
            round_ranking = custom_rank(round_rank_series)
            round_rank = round_ranking.get(manager_name, 0)

            round_contributions = -round_ranking.map({4: 50, 5: 50, 6: 100, 7: 100}).fillna(0)
            round_pool = -round_contributions.sum()
            round_first = round_ranking == 1
            round_second = round_ranking == 2
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
    for round_no in round_groups:
        round_label = f'Round {round_no}'
        round_weeks = round_groups[round_no]
        if not is_round_settlement_available(round_weeks, latest_confirmed_week):
            continue
        subtotal_column = (round_label, 'Subtotal', 'Round Subtotal')
        pay_to_column = (round_label, 'Settlement', 'Pay To')
        pay_amount_column = (round_label, 'Settlement', 'Pay Amount')
        settlements = calculate_waterfall_settlements(
            dict(zip(df[('Summary', '', 'Team Member')], df[subtotal_column]))
        )
        df[pay_to_column] = df[('Summary', '', 'Team Member')].map(
            lambda manager_name: settlements[manager_name][0]
        )
        df[pay_amount_column] = df[('Summary', '', 'Team Member')].map(
            lambda manager_name: settlements[manager_name][1]
        )
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
    from matplotlib.patches import Rectangle
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
                ordered_columns.extend(column for column in round_columns if column[1] == 'Settlement')
                ordered_columns.extend(column for column in round_columns if column[1].startswith('GW '))
            ordered_columns.extend(column for column in columns if column[0] == 'Summary' and column not in ordered_columns)
            ordered_columns.extend(column for column in columns if column not in ordered_columns)
            df_display = df_display[ordered_columns]
            settlement_columns = [
                column for column in ordered_columns if column[2] in ('Pay To', 'Pay Amount')
            ]
            for column in settlement_columns:
                df_display[column] = df_display[column].map(
                    lambda value: str(value).replace(', ', '\n') if pd.notna(value) else value
                )
            group_labels = []
            for column in ordered_columns[1:]:
                group_labels.append(
                    f'{column[0]} / {column[1].replace(" ", "")}'
                    if column[1].startswith('GW ')
                    else column[1] or 'Summary'
                )
            group_spans = []
            for index, group in enumerate(group_labels):
                if index == 0 or group != group_labels[index - 1]:
                    group_spans.append([group, index + 1, 1])
                else:
                    group_spans[-1][2] += 1

            table_headers = [
                ["" for _ in ordered_columns],
                ["" for _ in ordered_columns],
                ["" for _ in ordered_columns],
            ]
            if ordered_columns:
                round_names = list(dict.fromkeys(
                    column[0] for column in ordered_columns if column[0] != 'Summary'
                ))
                table_headers[0][0] = round_names[0] if len(round_names) == 1 else title
                table_headers[1][0] = "Team Member"
                for group, start, _ in group_spans:
                    table_headers[1][start] = group
                for index, column in enumerate(ordered_columns[1:], start=1):
                    table_headers[2][index] = str(column[2])
        else:
            table_headers = [[str(column) for column in df_display.columns]]
        
        # Ensure the output path ends with .png
        if not output_path.endswith('.png'):
            output_path = output_path.replace('.jpeg', '.png').replace('.html', '.png')
            if not output_path.endswith('.png'):
                output_path = output_path + '.png'
        
        # Create figure and axis with more space for the grouped headers.
        header_rows = len(table_headers)
        settlement_line_count = 1
        if is_grouped:
            settlement_line_count = max(
                (
                    str(value).count('\n') + 1
                    for column in settlement_columns
                    for value in df_display[column].dropna()
                ),
                default=1,
            )
        figure_height = max(
            3.2,
            len(df_display) * (0.38 + 0.24 * (settlement_line_count - 1))
            + (1.8 if is_grouped else 1.0),
        )

        table_data = []
        if not is_grouped:
            for header_row in table_headers:
                table_data.append(['\n'.join(wrap(header, width=14)) for header in header_row])
        for _, row in df_display.iterrows():
            table_data.append(row.tolist())

        # Size each column (in inches) from its widest header/content so text doesn't overlap.
        def column_width_inches(column_index, column):
            label = str(column[2]) if is_grouped else str(column)
            values = df_display[column].astype(str) if is_grouped else df_display.iloc[:, column_index].astype(str)
            longest_line = max(
                [len(label)] + [len(line) for value in values for line in value.split('\n')],
                default=len(label),
            )
            if column_index == 0:
                base = 1.6
            elif is_grouped and column[2] in ('Pay To', 'Pay Amount'):
                base = 1.2
            else:
                base = 0.7
            return max(base, 0.16 * longest_line)

        columns_iterable = list(df_display.columns)
        col_widths = [
            column_width_inches(index, column) for index, column in enumerate(columns_iterable)
        ]
        normalized_widths = [width / sum(col_widths) for width in col_widths]
        figure_width = max(20, sum(col_widths))
        fig, ax = plt.subplots(figsize=(figure_width, figure_height))
        ax.axis('tight')
        ax.axis('off')

        table = ax.table(
            cellText=table_data,
            cellLoc='center',
            loc='center' if not is_grouped else 'lower left',
            colWidths=normalized_widths,
            bbox=[0, 0, 1, 0.68] if is_grouped else None,
        )

        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1, 1.3 if header_rows == 1 else 1.05)

        # Style data rows with alternating colors
        first_data_row = 0 if is_grouped else header_rows
        for i in range(first_data_row, len(table_data)):
            for j in range(len(df_display.columns)):
                cell = table[(i, j)]
                cell.PAD = 0.02
                if j == 0:
                    cell.set_facecolor('#F2F2F2')
                elif (j - 1) % 2 == 0:
                    cell.set_facecolor('#FFF2CC')
                else:
                    cell.set_facecolor('#E2F0D9')
                is_round_subtotal = is_grouped and df_display.columns[j][2] == 'Round Subtotal'
                cell.set_text_props(ha='center', va='center', weight='bold' if is_round_subtotal else 'normal')

        if is_grouped:
            header_color = '#4472C4'
            edge_color = '#D9E2F3'
            boundaries = [0]
            for width in normalized_widths:
                boundaries.append(boundaries[-1] + width)

            def add_header_cell(x, y, width, height, label):
                ax.add_patch(Rectangle(
                    (x, y), width, height,
                    transform=ax.transAxes,
                    facecolor=header_color,
                    edgecolor=edge_color,
                    linewidth=0.8,
                ))
                ax.text(
                    x + width / 2,
                    y + height / 2,
                    '\n'.join(wrap(label, width=10)),
                    transform=ax.transAxes,
                    ha='center',
                    va='center',
                    color='white',
                    fontweight='bold',
                    fontsize=10,
                )

            add_header_cell(0, 0.92, 1, 0.06, table_headers[0][0])
            add_header_cell(0, 0.76, normalized_widths[0], 0.16, 'Team Member')
            for group, start, span in group_spans:
                add_header_cell(
                    boundaries[start],
                    0.84,
                    boundaries[start + span] - boundaries[start],
                    0.08,
                    group,
                )
            for column_index, column in enumerate(ordered_columns[1:], start=1):
                add_header_cell(boundaries[column_index], 0.72, normalized_widths[column_index], 0.12, str(column[2]))
        else:
            for row_index in range(header_rows):
                for column_index in range(len(df_display.columns)):
                    cell = table[(row_index, column_index)]
                    cell.PAD = 0.02
                    cell.set_facecolor('#4472C4')
                    cell.set_text_props(weight='bold', color='white', ha='center', va='center')
                    cell.set_height(0.06 if header_rows == 1 else 0.045)
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
