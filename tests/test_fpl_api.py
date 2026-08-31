import pandas as pd

from fpl_api import (
    build_player_selection_summary,
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
