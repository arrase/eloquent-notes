import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from eloquent_notes import config
from eloquent_notes.config import diff_configs


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> dict[str, Any]:
    """Fixture providing a temporary directory for config files."""
    config_dir = tmp_path / "config"
    prompts_dir = config_dir / "prompts"
    config_path = config_dir / "config.yaml"

    default_config_src = tmp_path / "default_config.yaml"
    default_config_src.write_text("audio:\n  channels: 1\nai:\n  model: gemma\n", encoding="utf-8")

    default_prompt_src = tmp_path / "default_prompt.md"
    default_prompt_src.write_text("System Prompt Content", encoding="utf-8")

    prompt_dst = prompts_dir / "transcription_system.md"

    files_to_copy = [
        (str(default_config_src), str(config_path)),
        (str(default_prompt_src), str(prompt_dst)),
    ]

    return {
        "config_dir": str(config_dir),
        "prompts_dir": str(prompts_dir),
        "config_path": str(config_path),
        "default_config_src": str(default_config_src),
        "files_to_copy": files_to_copy,
    }


def test_init_config_dir(tmp_config_dir: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Test init_config_dir creates directories and copies default files."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_config_dir["config_dir"])
    monkeypatch.setattr(config, "PROMPTS_DIR", tmp_config_dir["prompts_dir"])
    monkeypatch.setattr(config, "_FILES_TO_COPY", tmp_config_dir["files_to_copy"])

    config.init_config_dir()

    assert Path(tmp_config_dir["config_dir"]).is_dir()
    assert Path(tmp_config_dir["prompts_dir"]).is_dir()
    cfg_path = Path(tmp_config_dir["config_path"])
    assert cfg_path.is_file()

    content = cfg_path.read_text(encoding="utf-8")
    assert "audio:" in content

    # Test existing destination is not overwritten
    cfg_path.write_text("custom: true\n", encoding="utf-8")

    config.init_config_dir()
    content = cfg_path.read_text(encoding="utf-8")
    assert content == "custom: true\n"


def test_merge_configs() -> None:
    """Test recursive merging and type validation of base config and overrides."""
    base = {
        "audio": {"channels": 1, "beep_enabled": True, "beep_frequency": 440},
        "ai": {"model": "gemma", "context_length": 8192},
        "search": {"min_similarity": 0.6},
        "notes": {"type_colors": {"idea": "#C27821", "note": "#64748B"}},
    }
    overrides = {
        "audio": {"channels": 2, "beep_frequency": 880},
        "ai": {"model": "gemma4:e4b", "context_length": None},
        "search": {"min_similarity": 1},
        "notes": {"type_colors": {"idea": "#112233"}},
    }

    merged = config._merge_configs(base, overrides)

    assert merged["audio"]["channels"] == 2
    assert merged["audio"]["beep_frequency"] == 880
    assert merged["ai"]["model"] == "gemma4:e4b"
    assert merged["ai"]["context_length"] is None
    assert merged["search"]["min_similarity"] == 1
    assert merged["notes"]["type_colors"] == {"idea": "#112233", "note": "#64748B"}

    # Verify base was not mutated
    assert base["audio"]["channels"] == 1
    assert base["audio"]["beep_frequency"] == 440

    with pytest.raises(TypeError, match="Configuration section 'audio' must be a mapping"):
        config._merge_configs(base, {"audio": None})

    with pytest.raises(TypeError, match="Invalid configuration value for 'channels'"):
        config._merge_configs(base, {"audio": {"channels": None}})

    with pytest.raises(TypeError, match="Invalid configuration value for 'channels'"):
        config._merge_configs(base, {"audio": {"channels": True}})

    with pytest.raises(TypeError, match="Invalid configuration value for 'channels'"):
        config._merge_configs(base, {"audio": {"channels": "2"}})

    with pytest.raises(TypeError, match="Invalid configuration value for 'beep_enabled'"):
        config._merge_configs(base, {"audio": {"beep_enabled": 1}})

    with pytest.raises(TypeError, match="Invalid configuration value for 'model'"):
        config._merge_configs(base, {"ai": {"model": None}})

    with pytest.raises(ValueError, match="Invalid configuration value for 'idea'"):
        config._merge_configs(base, {"notes": {"type_colors": {"idea": "not-a-color"}}})

    with pytest.raises(ValueError, match="Unknown configuration key 'unknown_section'"):
        config._merge_configs(base, {"unknown_section": {}})

    with pytest.raises(ValueError, match="Unknown configuration key 'unknown_key'"):
        config._merge_configs(base, {"audio": {"unknown_key": 1}})

    with pytest.raises(ValueError, match="Unknown configuration key 'custom_type'"):
        config._merge_configs(base, {"notes": {"type_colors": {"custom_type": "#112233"}}})


@pytest.mark.parametrize(
    ("override", "key"),
    [
        ({"audio": {"beep_frequency": 0}}, "beep_frequency"),
        ({"audio": {"beep_frequency": -5}}, "beep_frequency"),
        ({"audio": {"channels": 0}}, "channels"),
        ({"audio": {"channels": 3}}, "channels"),
        ({"audio": {"beep_duration": float("inf")}}, "beep_duration"),
        ({"audio": {"beep_duration": float("nan")}}, "beep_duration"),
        ({"notes": {"type_colors": {"idea": "#112233\n"}}}, "idea"),
        ({"notes": {"columns": 0}}, "columns"),
        ({"notes": {"columns": -1}}, "columns"),
        ({"notes": {"folder": ""}}, "folder"),
        ({"notes": {"folder": "   "}}, "folder"),
        ({"ai": {"ollama_url": ""}}, "ollama_url"),
        ({"ai": {"ollama_url": "localhost:11434"}}, "ollama_url"),
        ({"ai": {"ollama_url": "ftp://localhost:11434"}}, "ollama_url"),
        ({"ai": {"ollama_url": "http://"}}, "ollama_url"),
        ({"ai": {"ollama_url": "https://"}}, "ollama_url"),
        ({"ai": {"ollama_url": "http://localhost:11434 "}}, "ollama_url"),
        ({"ai": {"ollama_url": "http://localhost:11434\n"}}, "ollama_url"),
        ({"ai": {"model": "  "}}, "model"),
        ({"ai": {"output_language": ""}}, "output_language"),
        ({"ai": {"context_length": 0}}, "context_length"),
        ({"ai": {"context_length": -100}}, "context_length"),
        ({"ai": {"keep_alive": ""}}, "keep_alive"),
        ({"ai": {"keep_alive": "5d"}}, "keep_alive"),
        ({"ai": {"keep_alive": "5m\n"}}, "keep_alive"),
        ({"ai": {"preload_keep_alive": "invalid"}}, "preload_keep_alive"),
        ({"search": {"keep_alive": "bad"}}, "keep_alive"),
        ({"search": {"embedding_model": ""}}, "embedding_model"),
        ({"ai": {"max_retries": -1}}, "max_retries"),
        ({"ai": {"request_timeout": 0}}, "request_timeout"),
        ({"ai": {"preload_timeout": 0}}, "preload_timeout"),
        ({"search": {"min_similarity": -0.1}}, "min_similarity"),
        ({"search": {"min_similarity": 1.1}}, "min_similarity"),
        ({"logging": {"level": "TRACE"}}, "level"),
        ({"logging": {"level": ""}}, "level"),
        ({"logging": {"max_mb": 0}}, "max_mb"),
        ({"logging": {"backup_count": -1}}, "backup_count"),
    ],
)
def test_merge_configs_rejects_invalid_domain_values(override: dict[str, Any], key: str) -> None:
    default_cfg = config.load_default_config()
    with pytest.raises(ValueError, match=f"Invalid configuration value for '{key}'"):
        config._merge_configs(default_cfg, override)


def test_merge_configs_accepts_valid_domain_boundaries() -> None:
    default_cfg = config.load_default_config()
    overrides = {
        "audio": {
            "channels": 2,
            "beep_enabled": False,
        },
        "notes": {"columns": 1, "folder": "/var/empty/notes"},
        "ai": {
            "ollama_url": "https://ollama.example.com:11434",
            "context_length": 512,
            "keep_alive": "-1",
            "preload_keep_alive": "500ms",
            "max_retries": 0,
            "request_timeout": 1,
            "preload_timeout": 1,
        },
        "search": {"keep_alive": "100µs", "min_similarity": 0.0},
        "logging": {"level": "debug", "max_mb": 1, "backup_count": 0},
    }
    merged = config._merge_configs(default_cfg, overrides)
    assert merged["audio"]["channels"] == 2
    assert merged["audio"]["beep_enabled"] is False
    assert merged["ai"]["max_retries"] == 0
    assert merged["search"]["min_similarity"] == 0.0
    assert merged["logging"]["backup_count"] == 0

    with pytest.raises(TypeError, match="Invalid configuration value for 'context_length'"):
        config._merge_configs(default_cfg, {"ai": {"context_length": True}})


def test_load_config(tmp_config_dir: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Test load_config merges default config and user config."""
    user_cfg_path = Path(tmp_config_dir["config_path"])
    user_cfg_content = "audio:\n  channels: 2\n"

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_config_dir["config_dir"])
    monkeypatch.setattr(config, "PROMPTS_DIR", tmp_config_dir["prompts_dir"])
    monkeypatch.setattr(config, "CONFIG_PATH", str(user_cfg_path))
    monkeypatch.setattr(config, "DEFAULT_CONFIG_SRC", tmp_config_dir["default_config_src"])
    monkeypatch.setattr(config, "_FILES_TO_COPY", [])

    Path(tmp_config_dir["config_dir"]).mkdir(parents=True, exist_ok=True)
    user_cfg_path.write_text(user_cfg_content, encoding="utf-8")

    cfg = config.load_config()
    assert cfg["audio"]["channels"] == 2
    assert cfg["ai"]["model"] == "gemma"

    user_cfg_path.write_text("", encoding="utf-8")

    cfg = config.load_config()
    assert cfg["audio"]["channels"] == 1
    assert cfg["ai"]["model"] == "gemma"


def test_load_config_non_dict_user_config(tmp_config_dir: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Test load_config raises TypeError if user config is not a YAML mapping."""
    user_cfg_path = Path(tmp_config_dir["config_path"])

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_config_dir["config_dir"])
    monkeypatch.setattr(config, "PROMPTS_DIR", tmp_config_dir["prompts_dir"])
    monkeypatch.setattr(config, "CONFIG_PATH", str(user_cfg_path))
    monkeypatch.setattr(config, "DEFAULT_CONFIG_SRC", tmp_config_dir["default_config_src"])
    monkeypatch.setattr(config, "_FILES_TO_COPY", [])

    Path(tmp_config_dir["config_dir"]).mkdir(parents=True, exist_ok=True)
    user_cfg_path.write_text("just a string\n", encoding="utf-8")

    with pytest.raises(TypeError, match="is not a valid YAML mapping"):
        config.load_config()

    user_cfg_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(TypeError, match="is not a valid YAML mapping"):
        config.load_config()


def test_load_and_atomic_write(tmp_path: Path) -> None:
    """Test loading and atomically writing text and binary files."""
    file_path = tmp_path / "sub" / "test.txt"
    content = "Hello World\nLine 2"

    config.atomic_write(str(file_path), content)
    assert file_path.is_file()

    loaded = config.load_file(str(file_path))
    assert loaded == content

    bin_path = tmp_path / "sub" / "test.bin"
    raw = b"\x00\x01\x02\xff"
    config.atomic_write(str(bin_path), raw)
    assert bin_path.read_bytes() == raw


def test_atomic_write_flat_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test atomic_write when path has no directory component."""
    monkeypatch.chdir(tmp_path)
    filename = "flat_file.txt"
    config.atomic_write(filename, "flat content")

    assert Path(filename).is_file()
    assert config.load_file(filename) == "flat content"


def test_save_config(tmp_config_dir: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Test saving configuration dictionary to user config path."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_config_dir["config_dir"])
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_config_dir["config_path"])

    data = {"audio": {"channels": 2}}
    config.save_config(data)

    cfg_path = Path(tmp_config_dir["config_path"])
    assert cfg_path.is_file()
    with cfg_path.open(encoding="utf-8") as f:
        loaded_data = yaml.safe_load(f)

    assert loaded_data == data


def test_load_default_config() -> None:
    """Verify the packaged default configuration values."""
    default_config = config.load_default_config()
    assert default_config["audio"]["channels"] == 1
    assert "capture_duration" not in default_config["audio"]
    assert default_config["audio"]["recording_hud_enabled"] is True
    assert default_config["notes"]["folder"] == "~/Documents/Eloquent Notes"
    assert default_config["notes"]["columns"] == 2
    assert default_config["notes"]["type_colors"] == {
        "note": "#64748B",
        "task": "#3B76B6",
        "idea": "#C27821",
        "reminder": "#C94A4D",
        "question": "#8258B8",
        "decision": "#2A8567",
    }
    assert default_config["search"]["embedding_model"] == "embeddinggemma-2:latest"
    assert default_config["search"]["keep_alive"] == "5m"
    assert default_config["search"]["min_similarity"] == 0.6


def test_prompt_paths_cover_every_copied_prompt() -> None:
    assert tuple(dst for _, dst in config._FILES_TO_COPY[1:]) == config.PROMPT_PATHS
    assert all(path.startswith(config.PROMPTS_DIR) for path in config.PROMPT_PATHS)
    assert tuple(config.PROMPT_DEFAULTS) == config.PROMPT_PATHS
    assert all(Path(src).is_file() for src in config.PROMPT_DEFAULTS.values())


def test_cache_dir_follows_xdg_cache_home() -> None:
    assert str(Path(os.environ["XDG_CACHE_HOME"], "eloquent-notes")) == config.CACHE_DIR


def test_get_data_home_follows_xdg_data_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")
    assert config.get_data_home() == "/custom/data"
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert config.get_data_home() == str(Path("~/.local/share").expanduser())


def test_diff_configs_identical() -> None:
    default = {"a": 1, "b": "hello", "c": True}
    current = {"a": 1, "b": "hello", "c": True}
    assert diff_configs(default, current) == {}


def test_diff_configs_scalar_changes() -> None:
    default = {"a": 1, "b": "hello", "c": True}
    current = {"a": 2, "b": "world", "c": True}
    assert diff_configs(default, current) == {"a": 2, "b": "world"}


def test_diff_configs_drops_obsolete_keys() -> None:
    default = {"a": 1}
    current = {"a": 1, "obsolete": 2}
    assert diff_configs(default, current) == {}


def test_diff_configs_bool_vs_int() -> None:
    default = {"flag": 0, "active": True}
    current = {"flag": False, "active": 1}
    assert diff_configs(default, current) == {"flag": False, "active": 1}


def test_diff_configs_nested_dicts() -> None:
    default = {
        "ai": {"model": "gemma", "context_length": 8192},
        "audio": {"channels": 1},
    }
    current = {
        "ai": {"model": "gemma4:e4b", "context_length": 8192},
        "audio": {"channels": 1},
    }
    assert diff_configs(default, current) == {"ai": {"model": "gemma4:e4b"}}


def test_diff_configs_none_values() -> None:
    default = {"context_length": 8192}
    current = {"context_length": None}
    assert diff_configs(default, current) == {"context_length": None}


def test_legacy_sample_rate_key_rejected() -> None:
    default_cfg = config.load_default_config()
    with pytest.raises(ValueError, match="Unknown configuration key 'sample_rate'"):
        config._merge_configs(default_cfg, {"audio": {"sample_rate": 16000}})


def test_legacy_capture_duration_key_rejected() -> None:
    default_cfg = config.load_default_config()
    with pytest.raises(ValueError, match="Unknown configuration key 'capture_duration'"):
        config._merge_configs(default_cfg, {"audio": {"capture_duration": 30}})
