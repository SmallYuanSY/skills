import json
import shutil

from conftest import NOW, OPEN_METEO, TAIPEI_DEFAULT, WEATHERKIT, WK_AVAILABLE_WITH_ALERTS, FakeHttp
from ww_config import save_config
from ww_http import HttpError
import weatherwise

OM = "https://api.open-meteo.com/"
WK = "https://weatherkit.apple.com/"
WK_AVAIL = "https://weatherkit.apple.com/api/v1/availability"


def run(argv, http, capsys):
    code = weatherwise.main(argv, http=http, now=NOW)
    return code, capsys.readouterr().out.strip()


def use_weatherkit(config_dir, p8_key):
    config_dir.mkdir(parents=True, exist_ok=True)
    key = config_dir / p8_key.name
    shutil.copy(p8_key, key)
    save_config(config_dir, {"default": TAIPEI_DEFAULT, "weatherkit": {
        "team_id": "TEAM123456", "key_id": "ABC123DEF4", "service_id": "dev.example.weather",
        "key_path": str(key)}})


def test_free_mode_with_default_place(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    code, out = run([], FakeHttp({OM: OPEN_METEO}), capsys)
    assert code == 0
    assert out.splitlines()[:3] == [
        "source: open-meteo",
        "location: 台北市 (25.033, 121.565) timezone=Asia/Taipei",
        "local_time: 2026-10-07T20:41 Wed",
    ]
    assert out.splitlines()[-1].startswith("alerts: unsupported")


def test_no_config_and_no_place_asks_where(config_dir, capsys):
    code, out = run([], FakeHttp({}), capsys)
    assert code == 1
    assert out.startswith("error: no_default_location\naction: ask the user where they are")


def test_weatherkit_mode(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    code, out = run([], FakeHttp({WK_AVAIL: WK_AVAILABLE_WITH_ALERTS, WK: WEATHERKIT}), capsys)
    assert code == 0
    assert out.splitlines()[0] == "source: weatherkit"
    assert out.splitlines()[-1] == "alerts: none"


def test_both_sources_give_the_same_weather_lines(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    _, free = run(["--days", "2"], FakeHttp({OM: OPEN_METEO}), capsys)
    use_weatherkit(config_dir, p8_key)
    _, paid = run(["--days", "2"], FakeHttp({WK_AVAIL: WK_AVAILABLE_WITH_ALERTS, WK: WEATHERKIT}), capsys)
    assert free.splitlines()[1:-1] == paid.splitlines()[1:-1]


def test_auth_failure_falls_back_with_a_notice(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    code, out = run([], FakeHttp({WK: HttpError(401), OM: OPEN_METEO}), capsys)
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("notice: weatherkit_auth_failed (HTTP 401), fell back to open-meteo;")
    assert "membership may have expired" in lines[0]
    assert lines[1] == "source: open-meteo"


def test_other_weatherkit_errors_do_not_fall_back(config_dir, p8_key, capsys):
    use_weatherkit(config_dir, p8_key)
    code, out = run([], FakeHttp({WK: HttpError(500), OM: OPEN_METEO}), capsys)
    assert code == 1
    assert out.startswith("error: service_error")


def test_incomplete_weatherkit_config_is_an_error_not_a_fallback(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT, "weatherkit": {"team_id": "T"}})
    code, out = run([], FakeHttp({OM: OPEN_METEO}), capsys)
    assert code == 1
    assert out.startswith("error: weatherkit_config_incomplete")


def test_days_are_clamped(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    for given, sent in [("0", "forecast_days=1"), ("20", "forecast_days=10")]:
        http = FakeHttp({OM: OPEN_METEO})
        run(["--days", given], http, capsys)
        assert sent in http.calls[-1][0]


def test_json_wraps_the_raw_data(config_dir, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    _, out = run(["--json"], FakeHttp({OM: OPEN_METEO}), capsys)
    data = json.loads(out)
    assert data["source"] == "open-meteo"
    assert data["data"]["daily"] == OPEN_METEO["daily"]
    assert "notice" not in data


def test_version(capsys):
    _, out = run(["--version"], FakeHttp({}), capsys)
    assert out == "weatherwise 1.0.0 · by SmallYuan · https://github.com/SmallYuanSY/skills"


def test_bad_arguments_are_reported_for_the_model(config_dir, capsys):
    code, out = run(["--days", "many"], FakeHttp({}), capsys)
    assert code == 1
    assert out.startswith("error: bad_arguments")


def test_lang_flag_reaches_the_geocoder(config_dir, capsys):
    http = FakeHttp({"https://nominatim.openstreetmap.org/": [{"display_name": "Tokyo, Japan", "lat": "35.68", "lon": "139.69"}],
                     OM: OPEN_METEO})
    run(["Tokyo", "--global", "--lang", "en"], http, capsys)
    assert "accept-language=en" in http.calls[0][0]
