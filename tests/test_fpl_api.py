from fpl_api import get_league_title, get_summary_columns


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
