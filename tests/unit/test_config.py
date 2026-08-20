"""Config precedence: environment < config file < CLI flag. All offline,
no API key needed -- credentials never flow through Config."""

from pathlib import Path

import pytest

from umlregen.config import Config, DEFAULT_CONFIDENCE_THRESHOLD, DEFAULT_MODEL_ID, load_config


def test_unset_values_fall_back_to_documented_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_var in (
        "UMLREGEN_MODEL_ID",
        "UMLREGEN_CACHE_DIR",
        "UMLREGEN_CONFIDENCE_THRESHOLD",
        "UMLREGEN_VERIFICATION_MAX_ROUNDS",
        "UMLREGEN_RENDER_FORMAT",
    ):
        monkeypatch.delenv(env_var, raising=False)

    config = load_config()

    assert config == Config()
    assert config.model_id == DEFAULT_MODEL_ID
    assert config.cache_dir == Path(".cache")
    assert config.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD  # T4.16: calibrated to 0.3
    assert config.verification_max_rounds == 2
    assert config.render_format == "svg"


def test_env_value_is_used_when_nothing_overrides_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UMLREGEN_VERIFICATION_MAX_ROUNDS", "5")
    assert load_config().verification_max_rounds == 5


def test_config_file_overrides_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UMLREGEN_VERIFICATION_MAX_ROUNDS", "5")
    config_file = tmp_path / "umlregen.toml"
    config_file.write_text("verification_max_rounds = 3\n", encoding="utf-8")

    config = load_config(config_path=config_file)

    assert config.verification_max_rounds == 3


def test_cli_flag_wins_over_config_file_and_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("UMLREGEN_VERIFICATION_MAX_ROUNDS", "5")
    config_file = tmp_path / "umlregen.toml"
    config_file.write_text("verification_max_rounds = 3\n", encoding="utf-8")

    config = load_config(
        config_path=config_file,
        cli_overrides={"verification_max_rounds": 1},
    )

    assert config.verification_max_rounds == 1


def test_cli_none_values_do_not_override_lower_layers(tmp_path: Path) -> None:
    config_file = tmp_path / "umlregen.toml"
    config_file.write_text("confidence_threshold = 0.6\n", encoding="utf-8")

    config = load_config(config_path=config_file, cli_overrides={"confidence_threshold": None})

    assert config.confidence_threshold == 0.6


def test_missing_config_file_path_is_harmless(tmp_path: Path) -> None:
    config = load_config(config_path=tmp_path / "does_not_exist.toml")
    assert config == Config()
