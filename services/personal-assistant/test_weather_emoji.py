from weather import _WMO
from weather_emoji import _EMOJI, emoji_for_condition


def test_all_wmo_conditions_have_emoji():
    for condition in _WMO.values():
        assert condition in _EMOJI


def test_known_conditions():
    assert emoji_for_condition("clear") == "☀️"
    assert emoji_for_condition("overcast") == "☁️"
    assert emoji_for_condition("rain") == "🌧️"
    assert emoji_for_condition("thunderstorm") == "⛈️"


def test_unknown_falls_back():
    assert emoji_for_condition("code-999") == "🌤️"
    assert emoji_for_condition("") == "🌤️"
