import os
import sys

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import BotManager


def test_ensure_commands_file_exists_recreates_missing_file(tmp_path):
    config = {
        "bots": {
            "TestBot": {
                "script": "main.py",
                "directory": "TestBot",
            }
        }
    }

    config_path = tmp_path / "bot_config.yaml"
    config_path.write_text(yaml.safe_dump(config))

    commands_file_path = tmp_path / "bot_commands.txt"

    manager = BotManager(
        config_path=str(config_path),
        commands_file=str(commands_file_path),
        db_path=str(tmp_path / "bot_states.db"),
    )

    os.remove(manager.commands_file_path)
    assert not os.path.exists(manager.commands_file_path)

    assert manager._ensure_commands_file_exists(log_if_created=True) is True
    assert os.path.exists(manager.commands_file_path)
