import os
import sys
import io
import threading
import time
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import BotManager


def test_stdin_mode_enabled_from_config(tmp_path):
    """Test that stdin mode can be enabled via config"""
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
            "stdin_mode": True,
        },
    }

    config_path = tmp_path / "bot_config.yaml"
    config_path.write_text(yaml.safe_dump(config))

    manager = BotManager(
        config_path=str(config_path),
        commands_file=str(tmp_path / "bot_commands.txt"),
        db_path=str(tmp_path / "bot_states.db"),
    )

    assert manager._is_stdin_mode_enabled() is True


def test_stdin_mode_defaults_to_false(tmp_path):
    """Test that stdin mode defaults to false when not configured"""
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

    assert manager._is_stdin_mode_enabled() is False


def test_execute_command_returns_status_and_message(tmp_path):
    """Test that _execute_command returns proper status and message"""
    bot_dir = tmp_path / "TestBot"
    bot_dir.mkdir()
    (bot_dir / "main.py").write_text("print('test')")

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

    # Test start command
    success, message = manager._execute_command("start TestBot")
    assert success is True
    assert "TestBot" in message
    assert "started" in message.lower()

    # Clean up
    manager.stop_bot("TestBot")


def test_execute_command_handles_invalid_command(tmp_path):
    """Test that _execute_command handles invalid commands properly"""
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

    # Test invalid command (too few parts)
    success, message = manager._execute_command("start")
    assert success is False
    assert "Invalid command format" in message

    # Test unknown action
    success, message = manager._execute_command("invalid TestBot")
    assert success is False
    assert "Unknown action" in message


def test_output_command_response_formats_correctly(tmp_path, capsys):
    """Test that command responses are formatted correctly"""
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

    # Test successful command response
    manager._output_command_response("start TestBot", True, "Bot TestBot started")
    captured = capsys.readouterr()
    assert "[ORCHESTRATOR] start TestBot: SUCCESS - Bot TestBot started" in captured.out

    # Test failed command response
    manager._output_command_response("stop TestBot", False, "Bot TestBot not running")
    captured = capsys.readouterr()
    assert "[ORCHESTRATOR] stop TestBot: FAILED - Bot TestBot not running" in captured.out
