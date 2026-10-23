import pytest

from ww_errors import ACTIONS, WwError
from ww_model import WMO, Place, Report, weatherkit_condition, wmo_condition

# WeatherKit condition codes that WMO codes map onto
WEATHERKIT_CODES = [
    "Clear", "MostlyClear", "PartlyCloudy", "Cloudy", "Foggy", "Drizzle", "FreezingDrizzle",
    "Rain", "HeavyRain", "FreezingRain", "Snow", "HeavySnow", "Thunderstorms",
]


def test_weatherkit_condition_splits_camel_case():
    assert weatherkit_condition("PartlyCloudy") == "Partly Cloudy"
    assert weatherkit_condition("Rain") == "Rain"


def test_every_wmo_name_matches_a_weatherkit_name():
    names = {weatherkit_condition(c) for c in WEATHERKIT_CODES}
    assert set(WMO.values()) <= names


def test_unknown_wmo_code_is_labelled_not_dropped():
    assert wmo_condition(42) == "Unknown (WMO 42)"


def test_every_error_code_has_an_action():
    assert all(ACTIONS.values())
    with pytest.raises(ValueError):
        WwError("not_a_code")


def test_place_new_fields_default_to_none():
    p = Place("x", 1, 2)
    assert (p.country_code, p.region, p.locality, p.district) == (None, None, None, None)


def test_report_has_no_alerts_and_next_hour_defaults_to_none():
    r = Report("open-meteo", None, [])
    assert not hasattr(r, "alerts")
    assert r.next_hour is None
