"""Unit tests for config GUI utility functions."""

from eloquent_notes.config_gui.utils import diff_configs


def test_diff_configs_identical():
    default = {"a": 1, "b": "hello", "c": True}
    current = {"a": 1, "b": "hello", "c": True}
    assert diff_configs(default, current) == {}


def test_diff_configs_scalar_changes():
    default = {"a": 1, "b": "hello", "c": True}
    current = {"a": 2, "b": "world", "c": True}
    assert diff_configs(default, current) == {"a": 2, "b": "world"}


def test_diff_configs_new_keys():
    default = {"a": 1}
    current = {"a": 1, "b": 2, "c": "new"}
    assert diff_configs(default, current) == {"b": 2, "c": "new"}


def test_diff_configs_bool_vs_int():
    default = {"flag": 0, "active": True}
    current = {"flag": False, "active": 1}
    diff = diff_configs(default, current)
    assert diff == {"flag": False, "active": 1}


def test_diff_configs_nested_dicts():
    default = {
        "ai": {"model": "gemma", "ctx": 10000},
        "audio": {"rate": 16000},
    }
    current = {
        "ai": {"model": "whisper", "ctx": 10000},
        "audio": {"rate": 16000},
    }
    assert diff_configs(default, current) == {"ai": {"model": "whisper"}}


def test_diff_configs_empty_nested_dict_override():
    default = {"ai": {"model": "gemma", "ctx": 10000}}
    current = {"ai": {}}
    assert diff_configs(default, current) == {"ai": {}}


def test_diff_configs_lists():
    default = {"items": [1, 2, 3]}
    current_= {"items": [1, 2, 3]}
    assert diff_configs(default, current_) == {}

    current_changed = {"items": [1, 2]}
    assert diff_configs(default, current_changed) == {"items": [1, 2]}


def test_diff_configs_none_values():
    default = {"val": None}
    current = {"val": "something"}
    assert diff_configs(default, current) == {"val": "something"}

    default2 = {"val": "something"}
    current2 = {"val": None}
    assert diff_configs(default2, current2) == {"val": None}
