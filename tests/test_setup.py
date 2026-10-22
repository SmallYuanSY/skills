import os
import stat

from conftest import NOW, TAIPEI_DEFAULT, WEATHERKIT, FakeHttp
from ww_config import load_config, save_config
from ww_http import HttpError
import weatherwise

NOMINATIM = "https://nominatim.openstreetmap.org/"
OM = "https://api.open-meteo.com/"
WK = "https://weatherkit.apple.com/"
TAICHUNG = [{"display_name": "臺中市, 臺灣", "lat": "24.1477", "lon": "120.6736",
             "address": {"city": "臺中市", "country": "臺灣", "country_code": "tw"}}]


def run(argv, http, capsys):
    code = weatherwise.main(["config", *argv], http=http, now=NOW)
    return code, capsys.readouterr().out.strip()


def wk_args(p8_key, *extra):
    return ["weatherkit", "--team-id", "TEAM123456", "--service-id", "dev.example.weather",
            "--key-file", str(p8_key), *extra]


def test_show_with_nothing_set(config_dir, capsys):
    code, out = run(["show"], FakeHttp({}), capsys)
    assert code == 0
    assert "default: none" in out
    assert "lang: zh-TW" in out
    assert "source: open-meteo" in out


def test_set_default_saves_and_asks_to_confirm(config_dir, capsys):
    code, out = run(["set-default", "台中"], FakeHttp({NOMINATIM: TAICHUNG, OM: {"timezone": "Asia/Taipei"}}), capsys)
    assert code == 0
    assert out.splitlines()[0] == "saved: default = 臺中市, 臺灣 (24.148, 120.674) timezone=Asia/Taipei"
    assert out.splitlines()[1].startswith("action: confirm with the user")
    assert load_config(config_dir)["default"] == {
        "name": "臺中市, 臺灣", "lat": 24.1477, "lon": 120.6736, "timezone": "Asia/Taipei",
        "country_code": "tw", "region": "臺中市", "locality": None, "district": None}


def test_set_default_unknown_place_writes_nothing(config_dir, capsys):
    code, out = run(["set-default", "Atlantis"], FakeHttp({NOMINATIM: []}), capsys)
    assert code == 1
    assert out.startswith("error: place_not_found")
    assert not (config_dir / "config.json").exists()


def test_set_lang(config_dir, capsys):
    assert run(["set-lang", "en"], FakeHttp({}), capsys) == (0, "saved: lang = en")
    assert load_config(config_dir)["lang"] == "en"
    code, out = run(["set-lang", "bad lang"], FakeHttp({}), capsys)
    assert code == 1 and out.startswith("error: unsupported_lang")


def test_weatherkit_copies_the_key_and_tests_it(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    http = FakeHttp({WK: WEATHERKIT})
    code, out = run(wk_args(p8_key), http, capsys)
    assert code == 0
    assert out == "saved: weatherkit (test request succeeded)\nsource: weatherkit"
    copy = config_dir / "AuthKey_ABC123DEF4.p8"
    assert copy.read_bytes() == p8_key.read_bytes()
    assert stat.S_IMODE(os.stat(copy).st_mode) == 0o600
    wk = load_config(config_dir)["weatherkit"]
    assert wk == {"team_id": "TEAM123456", "key_id": "ABC123DEF4", "service_id": "dev.example.weather",
                  "key_path": str(copy)}
    assert len(http.calls) == 1  # one weather request, nothing more


def test_weatherkit_setup_no_longer_saves_country_code(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    code, _ = run(wk_args(p8_key), FakeHttp({WK: WEATHERKIT}), capsys)
    assert code == 0
    assert "country_code" not in load_config(config_dir)["weatherkit"]


def test_weatherkit_rejected_key_saves_nothing(config_dir, p8_key, capsys):
    code, out = run(wk_args(p8_key), FakeHttp({OM: {"timezone": "Asia/Taipei"}, WK: HttpError(403)}), capsys)
    assert code == 1
    assert out.startswith("error: weatherkit_auth_failed (HTTP 403; team_id=TE…56 as given")
    assert not (config_dir / "config.json").exists()
    assert not (config_dir / "AuthKey_ABC123DEF4.p8").exists()


def test_weatherkit_needs_a_key_id_when_the_file_was_renamed(config_dir, p8_key, capsys):
    renamed = p8_key.with_name("mykey.p8")
    p8_key.rename(renamed)
    code, out = run(wk_args(renamed), FakeHttp({}), capsys)
    assert code == 1
    assert out.startswith("error: weatherkit_config_incomplete (key_id")


def test_weatherkit_missing_file(config_dir, tmp_path, capsys):
    code, out = run(["weatherkit", "--team-id", "T", "--service-id", "S", "--key-file", str(tmp_path / "nope.p8")],
                    FakeHttp({}), capsys)
    assert code == 1 and out.startswith("error: invalid_key_file")


def test_show_masks_ids_and_never_prints_the_key(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    run(wk_args(p8_key), FakeHttp({WK: WEATHERKIT}), capsys)
    _, out = run(["show"], FakeHttp({}), capsys)
    assert "source: weatherkit" in out
    assert "TE…56" in out and "TEAM123456" not in out
    assert "PRIVATE KEY" not in out


def test_remove_weatherkit(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    run(wk_args(p8_key), FakeHttp({WK: WEATHERKIT}), capsys)
    code, out = run(["weatherkit", "--remove"], FakeHttp({}), capsys)
    assert (code, out) == (0, "removed: weatherkit\nsource: open-meteo")
    assert "weatherkit" not in load_config(config_dir)
    assert not (config_dir / "AuthKey_ABC123DEF4.p8").exists()
    assert p8_key.exists()  # the user's own download is never touched


def saved_weatherkit(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    run(wk_args(p8_key), FakeHttp({WK: WEATHERKIT}), capsys)


def new_key(p8_key):
    path = p8_key.with_name("AuthKey_NEWKEY5678.p8")
    path.write_bytes(p8_key.read_bytes())
    return path


def test_new_key_keeps_the_saved_ids(config_dir, p8_key, capsys):
    saved_weatherkit(config_dir, p8_key, capsys)
    code, out = run(["weatherkit", "--key-file", str(new_key(p8_key))],
                    FakeHttp({WK: WEATHERKIT}), capsys)
    assert code == 0
    assert out.splitlines()[0] == "saved: weatherkit (test request succeeded; kept the saved team_id and service_id)"
    wk = load_config(config_dir)["weatherkit"]
    assert (wk["team_id"], wk["service_id"], wk["key_id"]) == ("TEAM123456", "dev.example.weather", "NEWKEY5678")
    assert wk["key_path"] == str(config_dir / "AuthKey_NEWKEY5678.p8")


def test_new_key_removes_the_old_copy(config_dir, p8_key, capsys):
    saved_weatherkit(config_dir, p8_key, capsys)
    run(["weatherkit", "--key-file", str(new_key(p8_key))],
        FakeHttp({WK: WEATHERKIT}), capsys)
    assert not (config_dir / "AuthKey_ABC123DEF4.p8").exists()
    assert (config_dir / "AuthKey_NEWKEY5678.p8").exists()
    assert p8_key.exists()  # the user's own download is never touched


def test_key_only_with_nothing_saved_says_ask_never_guess(config_dir, p8_key, capsys):
    code, out = run(["weatherkit", "--key-file", str(p8_key)], FakeHttp({}), capsys)
    assert code == 1
    assert out.startswith("error: weatherkit_config_incomplete (team_id, service_id)")
    assert "never guess" in out


def test_rejected_key_says_which_ids_were_used_and_not_to_guess(config_dir, p8_key, capsys):
    saved_weatherkit(config_dir, p8_key, capsys)
    code, out = run(["weatherkit", "--key-file", str(new_key(p8_key))],
                    FakeHttp({WK: HttpError(401)}), capsys)
    assert code == 1
    first, action = out.splitlines()
    assert first == ("error: weatherkit_auth_failed (HTTP 401; team_id=TE…56 from saved config, "
                     "service_id=de…er from saved config, key_id=NEWKEY5678)")
    assert "never guess" in action
    assert "TEAM123456" not in out
    assert load_config(config_dir)["weatherkit"]["key_id"] == "ABC123DEF4"  # old setup untouched


def test_key_copy_is_restrictive_without_relying_on_a_later_chmod(config_dir, p8_key, capsys, monkeypatch):
    # The copy must create the .p8 as 0600 from the start, not world-readable
    # for a window before a chmod. Neutralise chmod and a permissive umask so
    # only the creation mode remains.
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    monkeypatch.setattr(os, "chmod", lambda *a, **k: None)
    old = os.umask(0)
    try:
        run(wk_args(p8_key), FakeHttp({WK: WEATHERKIT}), capsys)
    finally:
        os.umask(old)
    copy = config_dir / "AuthKey_ABC123DEF4.p8"
    assert stat.S_IMODE(os.stat(copy).st_mode) == 0o600


def test_config_dir_is_private(config_dir, p8_key, capsys):
    save_config(config_dir, {"default": TAIPEI_DEFAULT})
    run(wk_args(p8_key), FakeHttp({WK: WEATHERKIT}), capsys)
    assert stat.S_IMODE(os.stat(config_dir).st_mode) == 0o700
