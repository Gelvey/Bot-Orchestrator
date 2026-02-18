import os
import sys
import threading
import time

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import BotManager


def test_process_command_file_dispatches_restart_action(tmp_path, monkeypatch):
    bot_dir = tmp_path / "TestBot"
    bot_dir.mkdir()

    config = {
        "bots": {
            "TestBot": {
                "script": "main.py",
                "directory": str(bot_dir),
            }
        }
    }

    config_path = tmp_path / "bot_config.yaml"
    config_path.write_text(yaml.safe_dump(config))

    commands_path = tmp_path / "bot_commands.txt"
    commands_path.write_text("restart TestBot\n")

    manager = BotManager(
        config_path=str(config_path),
        commands_file=str(commands_path),
        db_path=str(tmp_path / "bot_states.db"),
    )

    called = []

    def fake_restart(bot_name):
        called.append(bot_name)
        return True

    monkeypatch.setattr(manager, "restart_bot", fake_restart)

    original_sleep = time.sleep

    def stop_after_first_iteration(_seconds):
        manager.shutdown_event.set()
        return None

    monkeypatch.setattr(time, "sleep", stop_after_first_iteration)

    try:
        manager.shutdown_event.clear()
        manager._process_command_file()
    finally:
        monkeypatch.setattr(time, "sleep", original_sleep)

    assert called == ["TestBot"]


def test_restart_bot_starts_when_not_running(tmp_path, monkeypatch):
    bot_dir = tmp_path / "TestBot"
    bot_dir.mkdir()

    config = {
        "bots": {
            "TestBot": {
                "script": "main.py",
                "directory": str(bot_dir),
            }
        }
    }

    config_path = tmp_path / "bot_config.yaml"
    config_path.write_text(yaml.safe_dump(config))

    manager = BotManager(
        config_path=str(config_path),
        commands_file=str(tmp_path / "bot_commands.txt"),
        db_path=str(tmp_path / "bot_states.db"),
    )

    start_calls = []

    def fake_start(bot_name):
        start_calls.append(bot_name)
        return True

    monkeypatch.setattr(manager, "start_bot", fake_start)

    assert manager.restart_bot("TestBot") is True
    assert start_calls == ["TestBot"]


def test_process_command_file_ignores_comment_lines(tmp_path):
    bot_dir = tmp_path / "TestBot"
    bot_dir.mkdir()

    config = {
        "bots": {
            "TestBot": {
                "script": "main.py",
                "directory": str(bot_dir),
            }
        }
    }

    config_path = tmp_path / "bot_config.yaml"
    config_path.write_text(yaml.safe_dump(config))

    commands_path = tmp_path / "bot_commands.txt"
    commands_path.write_text("# header\n# another comment\n")

    manager = BotManager(
        config_path=str(config_path),
        commands_file=str(commands_path),
        db_path=str(tmp_path / "bot_states.db"),
    )

    manager.shutdown_event.clear()

    command_thread = threading.Thread(target=manager._process_command_file, daemon=True)
    command_thread.start()

    manager.shutdown_event.set()
    command_thread.join(timeout=2)

    with open(manager.commands_file_path, "r") as command_file:
        remaining = command_file.read().strip()

    assert remaining == ""


def test_discord_message_suppression_enabled_from_global_settings(tmp_path):
    bot_dir = tmp_path / "TestBot"
    bot_dir.mkdir()

    config = {
        "bots": {
            "TestBot": {
                "script": "main.py",
                "directory": str(bot_dir),
            }
        },
        "global_settings": {
            "suppress_discord_messages": True,
        },
    }

    config_path = tmp_path / "bot_config.yaml"
    config_path.write_text(yaml.safe_dump(config))

    manager = BotManager(
        config_path=str(config_path),
        commands_file=str(tmp_path / "bot_commands.txt"),
        db_path=str(tmp_path / "bot_states.db"),
    )

    assert manager._is_discord_message_suppression_enabled() is True


def test_discord_message_suppression_defaults_false_for_invalid_global_value(tmp_path):
    bot_dir = tmp_path / "TestBot"
    bot_dir.mkdir()

    config = {
        "bots": {
            "TestBot": {
                "script": "main.py",
                "directory": str(bot_dir),
            }
        },
        "global_settings": {
            "suppress_discord_messages": "yes",
        },
    }

    config_path = tmp_path / "bot_config.yaml"
    config_path.write_text(yaml.safe_dump(config))

    manager = BotManager(
        config_path=str(config_path),
        commands_file=str(tmp_path / "bot_commands.txt"),
        db_path=str(tmp_path / "bot_states.db"),
    )

    assert manager._is_discord_message_suppression_enabled() is False


def test_should_suppress_discord_output_line_when_enabled(tmp_path):
    bot_dir = tmp_path / "TestBot"
    bot_dir.mkdir()

    config = {
        "bots": {
            "TestBot": {
                "script": "main.py",
                "directory": str(bot_dir),
            }
        }
    }

    config_path = tmp_path / "bot_config.yaml"
    config_path.write_text(yaml.safe_dump(config))

    manager = BotManager(
        config_path=str(config_path),
        commands_file=str(tmp_path / "bot_commands.txt"),
        db_path=str(tmp_path / "bot_states.db"),
    )

    assert manager._should_suppress_discord_output_line(
        "Discord message received from user", True
    ) is True
    assert manager._should_suppress_discord_output_line(
        "Discord message received from user", False
    ) is False
    assert manager._should_suppress_discord_output_line(
        "Discord gateway connected", True
    ) is False
