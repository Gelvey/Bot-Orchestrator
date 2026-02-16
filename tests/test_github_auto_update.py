import subprocess
import os
import sys
from unittest.mock import patch

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import BotManager


def _create_manager(tmp_path, auto_update=True, extra_bot_config=None):
    bot_dir = tmp_path / "TestBot"
    bot_dir.mkdir()
    (bot_dir / ".git").mkdir()

    bot_config = {
        "script": "main.py",
        "directory": str(bot_dir),
        "repo_url": "https://github.com/example/repo.git",
        "auto_update": auto_update,
    }
    if extra_bot_config:
        bot_config.update(extra_bot_config)

    config = {
        "bots": {
            "TestBot": bot_config
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
            subprocess.CompletedProcess(["git", "rev-parse", "--show-toplevel"], 0, stdout=directory + "\n", stderr=""),
            subprocess.CompletedProcess(["git", "status", "--porcelain"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(
                ["git", "remote", "get-url", "origin"], 0, stdout=bot_config["repo_url"] + "\n", stderr=""
            ),
            subprocess.CompletedProcess(["git", "pull", "--ff-only"], 0, stdout="Already up to date.\n", stderr=""),
        ]

        manager._update_bot_from_repo("TestBot", bot_config, directory)

    assert run_mock.call_count == 4
    assert run_mock.call_args_list[3][0][0] == ["git", "pull", "--ff-only"]


def test_update_bot_from_repo_skips_pull_with_local_changes(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=True)
    bot_config = manager.config["bots"]["TestBot"]

    with patch("main.subprocess.run") as run_mock:
        run_mock.side_effect = [
            subprocess.CompletedProcess(["git", "rev-parse", "--show-toplevel"], 0, stdout=directory + "\n", stderr=""),
            subprocess.CompletedProcess(["git", "status", "--porcelain"], 0, stdout=" M main.py\n", stderr=""),
        ]

        manager._update_bot_from_repo("TestBot", bot_config, directory)

    assert run_mock.call_count == 2


def test_update_bot_from_repo_skips_when_disabled(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=False)
    bot_config = manager.config["bots"]["TestBot"]

    with patch("main.subprocess.run") as run_mock:
        manager._update_bot_from_repo("TestBot", bot_config, directory)

    run_mock.assert_not_called()


def test_update_bot_from_repo_skips_when_not_in_git_repo(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=True)
    bot_config = manager.config["bots"]["TestBot"]

    with patch("main.subprocess.run") as run_mock:
        run_mock.side_effect = [
            subprocess.CompletedProcess(
                ["git", "rev-parse", "--show-toplevel"],
                128,
                stdout="",
                stderr="fatal: not a git repository",
            ),
            subprocess.CompletedProcess(
                ["git", "init"],
                1,
                stdout="",
                stderr="fatal: not a git repository",
            ),
        ]

        manager._update_bot_from_repo("TestBot", bot_config, directory)

    assert run_mock.call_count == 2


def test_update_bot_from_repo_bootstraps_and_pulls_when_not_git_repo(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=True)
    bot_config = manager.config["bots"]["TestBot"]

    with patch("main.subprocess.run") as run_mock:
        run_mock.side_effect = [
            subprocess.CompletedProcess(["git", "rev-parse", "--show-toplevel"], 128, stdout="", stderr="fatal"),
            subprocess.CompletedProcess(["git", "init"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git", "remote", "add", "origin", bot_config["repo_url"]], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git", "fetch", "origin"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], 0, stdout="origin/main\n", stderr=""),
            subprocess.CompletedProcess(["git", "reset", "--hard", "origin/main"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git", "rev-parse", "--show-toplevel"], 0, stdout=directory + "\n", stderr=""),
            subprocess.CompletedProcess(["git", "status", "--porcelain"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(
                ["git", "remote", "get-url", "origin"], 0, stdout=bot_config["repo_url"] + "\n", stderr=""
            ),
            subprocess.CompletedProcess(["git", "pull", "--ff-only"], 0, stdout="Already up to date.\n", stderr=""),
        ]

        manager._update_bot_from_repo("TestBot", bot_config, directory)

    assert run_mock.call_count == 10
    assert run_mock.call_args_list[9][0][0] == ["git", "pull", "--ff-only"]


def test_update_bot_from_repo_force_sync_when_local_changes(tmp_path):
    manager, directory = _create_manager(
        tmp_path,
        auto_update=True,
        extra_bot_config={"force_sync": True, "preserve_files": [".env", "config/local.yaml"]},
    )
    bot_config = manager.config["bots"]["TestBot"]

    with patch("main.subprocess.run") as run_mock, patch.object(manager, "_force_sync_bot_repo", return_value=True) as force_mock:
        run_mock.side_effect = [
            subprocess.CompletedProcess(["git", "rev-parse", "--show-toplevel"], 0, stdout=directory + "\n", stderr=""),
            subprocess.CompletedProcess(["git", "status", "--porcelain"], 0, stdout=" M main.py\n", stderr=""),
        ]

        manager._update_bot_from_repo("TestBot", bot_config, directory)

    assert run_mock.call_count == 2
    force_mock.assert_called_once_with(
        "TestBot",
        directory,
        bot_config["repo_url"],
        [".env", "config/local.yaml"],
    )
