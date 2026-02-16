import subprocess
import os
import sys
from unittest.mock import patch

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import BotManager


def _create_manager(tmp_path, auto_update=True):
    bot_dir = tmp_path / "TestBot"
    bot_dir.mkdir()
    (bot_dir / ".git").mkdir()

    config = {
        "bots": {
            "TestBot": {
                "script": "main.py",
                "directory": str(bot_dir),
                "repo_url": "https://github.com/example/repo.git",
                "auto_update": auto_update,
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
    return manager, str(bot_dir)


def test_update_bot_from_repo_pulls_when_clean(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=True)
    bot_config = manager.config["bots"]["TestBot"]

    with patch("main.subprocess.run") as run_mock:
        run_mock.side_effect = [
            subprocess.CompletedProcess(["git", "status", "--porcelain"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(
                ["git", "remote", "get-url", "origin"], 0, stdout=bot_config["repo_url"] + "\n", stderr=""
            ),
            subprocess.CompletedProcess(["git", "pull", "--ff-only"], 0, stdout="Already up to date.\n", stderr=""),
        ]

        manager._update_bot_from_repo("TestBot", bot_config, directory)

    assert run_mock.call_count == 3
    assert run_mock.call_args_list[2][0][0] == ["git", "pull", "--ff-only"]


def test_update_bot_from_repo_skips_pull_with_local_changes(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=True)
    bot_config = manager.config["bots"]["TestBot"]

    with patch("main.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["git", "status", "--porcelain"], 0, stdout=" M main.py\n", stderr=""
        )

        manager._update_bot_from_repo("TestBot", bot_config, directory)

    assert run_mock.call_count == 1


def test_update_bot_from_repo_skips_when_disabled(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=False)
    bot_config = manager.config["bots"]["TestBot"]

    with patch("main.subprocess.run") as run_mock:
        manager._update_bot_from_repo("TestBot", bot_config, directory)

    run_mock.assert_not_called()
