import pytest

from routine_core import VERSION
from routine_core.errors import ACTIONS, BUSINESS, STORAGE, USAGE, RkError, error_data, render_error


def test_version_is_semver():
    assert VERSION.count(".") == 2


def test_every_code_has_an_exit_code_and_an_action():
    for code, (exit_code, action) in ACTIONS.items():
        assert exit_code in (USAGE, BUSINESS, STORAGE), code
        assert action and not action.endswith("."), code


def test_unknown_code_is_a_programming_error():
    with pytest.raises(ValueError):
        RkError("no_such_code")


def test_render_error_has_code_detail_and_action():
    err = RkError("unknown_item", 'no item named "Vit"; existing: Vitamin D')
    assert err.exit_code == BUSINESS
    assert render_error(err) == (
        'error: unknown_item (no item named "Vit"; existing: Vitamin D)\n'
        f"action: {ACTIONS['unknown_item'][1]}"
    )


def test_error_data_for_json():
    err = RkError("data_unavailable", "/x")
    assert error_data(err) == {"error": "data_unavailable", "detail": "/x", "action": ACTIONS["data_unavailable"][1]}
