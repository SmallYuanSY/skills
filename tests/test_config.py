import json
import os
import stat

import pytest

import ww_config
from ww_config import KEY_FILE_NAME, load_config, mask, resolve_lang, save_config, weatherkit_settings
from ww_errors import WwError


def test_config_dir_follows_the_env(config_dir):
    assert ww_config.config_dir() == config_dir


def test_missing_file_is_an_empty_config(config_dir):
    assert load_config(config_dir) == {}


def test_broken_json_is_config_invalid(config_dir):
    config_dir.mkdir()
    (config_dir / "config.json").write_text("{not json")
    with pytest.raises(WwError) as e:
        load_config(config_dir)
    assert e.value.code == "config_invalid"


def test_save_round_trips_with_private_permissions(config_dir):
    save_config(config_dir, {"lang": "en"})
    assert load_config(config_dir) == {"lang": "en"}
    assert stat.S_IMODE(os.stat(config_dir / "config.json").st_mode) == 0o600


def test_failed_save_keeps_the_old_file(config_dir, monkeypatch):
    save_config(config_dir, {"lang": "en"})

    def boom(*_):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        save_config(config_dir, {"lang": "ja"})
    assert json.loads((config_dir / "config.json").read_text()) == {"lang": "en"}
    assert [p.name for p in config_dir.iterdir()] == ["config.json"]


def test_lang_priority_and_validation():
    assert resolve_lang(None, {}) == "zh-TW"
    assert resolve_lang(None, {"lang": "ja"}) == "ja"
    assert resolve_lang("en", {"lang": "ja"}) == "en"
    with pytest.raises(WwError) as e:
        resolve_lang("not a lang!", {})
    assert e.value.code == "unsupported_lang"


def test_weatherkit_settings(tmp_path):
    key = tmp_path / "AuthKey_K.p8"
    key.write_text("x")
    full = {"team_id": "T", "key_id": "K", "service_id": "S", "key_path": str(key)}
    assert weatherkit_settings({}) is None
    assert weatherkit_settings({"weatherkit": full}) == full
    with pytest.raises(WwError) as e:
        weatherkit_settings({"weatherkit": {"team_id": "T"}})
    assert (e.value.code, e.value.detail) == ("weatherkit_config_incomplete", "key_id, service_id, key_path")
    with pytest.raises(WwError) as e:
        weatherkit_settings({"weatherkit": {**full, "key_path": str(tmp_path / "gone.p8")}})
    assert e.value.code == "weatherkit_key_missing"


def test_mask_keeps_only_the_ends():
    assert mask("TEAMID1234") == "TE…34"
    assert mask("abc") == "…"


def test_key_file_name():
    assert KEY_FILE_NAME.match("AuthKey_ABC123DEF4.p8")[1] == "ABC123DEF4"
    assert KEY_FILE_NAME.match("mykey.p8") is None
