import os
import sys
import threading

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import BotManager


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
