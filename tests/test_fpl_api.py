import pandas as pd

from fpl_api import (
    build_player_selection_summary,
    calculate_live_team_points,
    get_gameweek_data_status,
    get_league_title,
    get_summary_columns,
)


def test_get_league_title_uses_selected_league_name():
    assert get_league_title(185376, "Prison Breaker") == "Prison Breaker FPL 26/27"
    assert get_league_title(123456, "Guttene") == "Guttene FPL 26/27"


def test_prison_tokens_only_for_prison_breaker():
    base_columns = [
        "Ranking",
        "Manager Name",
        "Team Name",
        "Team GW Points",
        "Prison token",
        "Transfers Made",
        "Card Used",
    ]

    assert "Prison token" in get_summary_columns(185376, base_columns)
    assert "Prison token" not in get_summary_columns(123456, base_columns)


def test_player_selection_summary_is_sorted_by_selection_count():
    players = {
        1: {'web_name': 'Alpha', 'team': 10, 'element_type': 3},
        2: {'web_name': 'Beta', 'team': 11, 'element_type': 4},
    }
    teams = {10: 'Club A', 11: 'Club B'}
    positions = {3: 'MID', 4: 'FWD'}
    picks = [
        [{'element': 1}, {'element': 2}],
        [{'element': 1}],
    ]

    result = build_player_selection_summary(picks, players, teams, positions)

    expected = pd.DataFrame([
        {'Player Name': 'Alpha', 'Club': 'Club A', 'Position': 'MID', 'No. of Selections': 2},
        {'Player Name': 'Beta', 'Club': 'Club B', 'Position': 'FWD', 'No. of Selections': 1},
    ])
    pd.testing.assert_frame_equal(result, expected)


def test_gameweek_data_status_uses_live_for_current_week_and_confirmed_for_finished_week():
    events = [
        {'id': 1, 'finished': True},
        {'id': 2, 'is_current': True, 'finished': False},
        {'id': 3, 'finished': False},
    ]

    assert get_gameweek_data_status(events, 1) == 'confirmed'
    assert get_gameweek_data_status(events, 2) == 'live'
    assert get_gameweek_data_status(events, 3) == 'upcoming'


def test_calculate_live_team_points_keeps_zero_multiplier_bench_players_at_zero():
    picks = [
        {'element': 165, 'multiplier': 2},
        {'element': 426, 'multiplier': 1},
        {'element': 301, 'multiplier': 0},
        {'element': 525, 'multiplier': 0},
    ]
    live_points = {165: 9, 426: 23, 301: 0, 525: 2}

    assert calculate_live_team_points(picks, live_points) == 41


def test_round_rank_includes_live_gameweek_for_in_progress_round():
    current_live_week = 2
    latest_confirmed_week = 1
    round_weeks = [1, 2, 3, 4]

    weekly_scores = {
        'A': [10, 50, 0, 0],
        'B': [20, 40, 0, 0],
    }
    weekly_tokens = {
        'A': [0, 0, 0, 0],
        'B': [0, 0, 0, 0],
    }

    round_points_by_manager = {
        manager: sum(
            weekly_scores[manager][week - 1]
            for week in round_weeks
            if week <= latest_confirmed_week or week == current_live_week
        )
        for manager in weekly_scores
    }

    assert round_points_by_manager == {'A': 60, 'B': 60}
