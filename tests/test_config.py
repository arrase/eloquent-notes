"""Unit tests for eloquent_notes.config."""

import os
import shutil

import pytest
import yaml

from eloquent_notes import config


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Fixture providing a temporary directory for config files."""
    config_dir = tmp_path / "config"
    prompts_dir = config_dir / "prompts"
    templates_dir = config_dir / "templates"
    config_path = config_dir / "config.yaml"

    default_config_src = tmp_path / "default_config.yaml"
    default_config_src.write_text("audio:\n  device: 0\nai:\n  model: gemma\n", encoding="utf-8")

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
        "templates_dir": str(templates_dir),
        "config_path": str(config_path),
        "default_config_src": str(default_config_src),
        "files_to_copy": files_to_copy,
    }


def test_init_config_dir(tmp_config_dir, monkeypatch):
    """Test init_config_dir creates directories and copies default files."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_config_dir["config_dir"])
    monkeypatch.setattr(config, "PROMPTS_DIR", tmp_config_dir["prompts_dir"])
    monkeypatch.setattr(config, "TEMPLATES_DIR", tmp_config_dir["templates_dir"])
    monkeypatch.setattr(config, "_FILES_TO_COPY", tmp_config_dir["files_to_copy"])

    config.init_config_dir()

    assert os.path.isdir(tmp_config_dir["config_dir"])
    assert os.path.isdir(tmp_config_dir["prompts_dir"])
    assert os.path.isdir(tmp_config_dir["templates_dir"])
    assert os.path.isfile(tmp_config_dir["config_path"])

    with open(tmp_config_dir["config_path"], "r", encoding="utf-8") as f:
        content = f.read()
    assert "audio:" in content

    # Test existing destination is not overwritten
    with open(tmp_config_dir["config_path"], "w", encoding="utf-8") as f:
        f.write("custom: true\n")

    config.init_config_dir()
    with open(tmp_config_dir["config_path"], "r", encoding="utf-8") as f:
        content = f.read()
    assert content == "custom: true\n"


def test_merge_configs():
    """Test recursive merging of base config and overrides."""
    base = {
        "audio": {"device": 0, "sample_rate": 16000},
        "ui": {"theme": "dark"},
    }
    overrides = {
        "audio": {"device": 1},
        "ui": {"theme": "light", "font_size": 12},
        "new_section": {"key": "val"},
    }

    merged = config._merge_configs(base, overrides)

    assert merged["audio"]["device"] == 1
    assert merged["audio"]["sample_rate"] == 16000
    assert merged["ui"]["theme"] == "light"
    assert merged["ui"]["font_size"] == 12
    assert merged["new_section"]["key"] == "val"

    # Verify base was not mutated
    assert base["audio"]["device"] == 0


def test_load_config(tmp_config_dir, monkeypatch):
    """Test load_config merges default config and user config."""
    user_cfg_path = tmp_config_dir["config_path"]
    user_cfg_content = "audio:\n  device: 5\n"

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_config_dir["config_dir"])
    monkeypatch.setattr(config, "PROMPTS_DIR", tmp_config_dir["prompts_dir"])
    monkeypatch.setattr(config, "TEMPLATES_DIR", tmp_config_dir["templates_dir"])
    monkeypatch.setattr(config, "CONFIG_PATH", user_cfg_path)
    monkeypatch.setattr(config, "DEFAULT_CONFIG_SRC", tmp_config_dir["default_config_src"])
    monkeypatch.setattr(config, "_FILES_TO_COPY", [])

    os.makedirs(tmp_config_dir["config_dir"], exist_ok=True)
    with open(user_cfg_path, "w", encoding="utf-8") as f:
        f.write(user_cfg_content)

    cfg = config.load_config()
    assert cfg["audio"]["device"] == 5
    assert cfg["ai"]["model"] == "gemma"


def test_load_config_non_dict_user_config(tmp_config_dir, monkeypatch):
    """Test load_config raises ValueError if user config is not a YAML mapping."""
    user_cfg_path = tmp_config_dir["config_path"]

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_config_dir["config_dir"])
    monkeypatch.setattr(config, "PROMPTS_DIR", tmp_config_dir["prompts_dir"])
    monkeypatch.setattr(config, "TEMPLATES_DIR", tmp_config_dir["templates_dir"])
    monkeypatch.setattr(config, "CONFIG_PATH", user_cfg_path)
    monkeypatch.setattr(config, "DEFAULT_CONFIG_SRC", tmp_config_dir["default_config_src"])
    monkeypatch.setattr(config, "_FILES_TO_COPY", [])

    os.makedirs(tmp_config_dir["config_dir"], exist_ok=True)
    with open(user_cfg_path, "w", encoding="utf-8") as f:
        f.write("just a string\n")

    with pytest.raises(ValueError, match="is not a valid YAML mapping"):
        config.load_config()


def test_load_and_save_file(tmp_path):
    """Test loading and saving text files."""
    file_path = tmp_path / "sub" / "test.txt"
    content = "Hello World\nLine 2"

    config.save_file(str(file_path), content)
    assert os.path.isfile(file_path)

    loaded = config.load_file(str(file_path))
    assert loaded == content


def test_save_file_flat_path(tmp_path, monkeypatch):
    """Test save_file when path has no directory component."""
    monkeypatch.chdir(tmp_path)
    filename = "flat_file.txt"
    config.save_file(filename, "flat content")

    assert os.path.isfile(filename)
    assert config.load_file(filename) == "flat content"


def test_save_config(tmp_config_dir, monkeypatch):
    """Test saving configuration dictionary to user config path."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_config_dir["config_dir"])
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_config_dir["config_path"])

    data = {"test_key": "test_val", "nested": {"a": 1}}
    config.save_config(data)

    assert os.path.isfile(tmp_config_dir["config_path"])
    with open(tmp_config_dir["config_path"], "r", encoding="utf-8") as f:
        loaded_data = yaml.safe_load(f)

    assert loaded_data == data


def test_default_config_audio_capture_duration():
    """Verify that the packaged default config.yaml specifies capture_duration as 30."""
    with open(config.DEFAULT_CONFIG_SRC, "r", encoding="utf-8") as f:
        default_config = yaml.safe_load(f)
    assert "audio" in default_config
    assert default_config["audio"]["capture_duration"] == 30

