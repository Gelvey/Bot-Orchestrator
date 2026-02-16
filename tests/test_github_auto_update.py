import os
import sys
from unittest.mock import patch
import pytest

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import BotManager


def _create_manager(tmp_path, auto_update=True, extra_bot_config=None):
    bot_dir = tmp_path / "TestBot"
    bot_dir.mkdir()

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

    with patch.object(manager, "_sync_bot_from_archive", return_value=True) as sync_mock:
        manager._update_bot_from_repo("TestBot", bot_config, directory)

    sync_mock.assert_called_once_with(
        "TestBot",
        directory,
        bot_config["repo_url"],
        [],
        False,
        None,
    )


def test_update_bot_from_repo_skips_pull_with_local_changes(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=True)
    bot_config = manager.config["bots"]["TestBot"]

    with patch.object(manager, "_sync_bot_from_archive", return_value=True) as sync_mock:
        manager._update_bot_from_repo("TestBot", bot_config, directory)

    sync_mock.assert_called_once()


def test_update_bot_from_repo_skips_when_disabled(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=False)
    bot_config = manager.config["bots"]["TestBot"]

    with patch.object(manager, "_sync_bot_from_archive", return_value=True) as sync_mock:
        manager._update_bot_from_repo("TestBot", bot_config, directory)

    sync_mock.assert_not_called()


def test_update_bot_from_repo_skips_when_directory_missing(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=True)
    bot_config = manager.config["bots"]["TestBot"]
    missing_dir = os.path.join(directory, "missing")

    with patch.object(manager, "_sync_bot_from_archive", return_value=True) as sync_mock:
        manager._update_bot_from_repo("TestBot", bot_config, missing_dir)

    sync_mock.assert_not_called()


def test_update_bot_from_repo_uses_force_sync_and_preserve_files(tmp_path):
    manager, directory = _create_manager(tmp_path, auto_update=True)
    bot_config = manager.config["bots"]["TestBot"]
    bot_config["force_sync"] = True
    bot_config["preserve_files"] = [".env", "config/local.yaml"]
    bot_config["repo_branch"] = "develop"

    with patch.object(manager, "_sync_bot_from_archive", return_value=True) as sync_mock:
        manager._update_bot_from_repo("TestBot", bot_config, directory)

    sync_mock.assert_called_once_with(
        "TestBot",
        directory,
        bot_config["repo_url"],
        [".env", "config/local.yaml"],
        True,
        "develop",
    )


def test_build_github_archive_urls_from_standard_repo_url(tmp_path):
    manager, _ = _create_manager(tmp_path, auto_update=True)

    urls = manager._build_github_archive_urls("https://github.com/Gelvey/Task-Master.git")

    assert urls == [
        "https://codeload.github.com/Gelvey/Task-Master/zip/refs/heads/main",
        "https://codeload.github.com/Gelvey/Task-Master/zip/refs/heads/master",
    ]


def test_build_github_archive_urls_prefers_explicit_branch(tmp_path):
    manager, _ = _create_manager(tmp_path, auto_update=True)

    urls = manager._build_github_archive_urls("https://github.com/Gelvey/Task-Master", preferred_branch="develop")

    assert urls[0] == "https://codeload.github.com/Gelvey/Task-Master/zip/refs/heads/develop"


def test_update_bot_from_repo_skips_when_target_is_orchestrator_directory(tmp_path):
    manager, _ = _create_manager(tmp_path, auto_update=True)
    bot_config = manager.config["bots"]["TestBot"]

    with patch.object(manager, "_sync_bot_from_archive", return_value=True) as sync_mock:
        manager._update_bot_from_repo("TestBot", bot_config, manager.base_dir)

    sync_mock.assert_not_called()


def test_update_bot_from_repo_skips_when_target_symlinks_to_orchestrator(tmp_path):
    manager, _ = _create_manager(tmp_path, auto_update=True)
    bot_config = manager.config["bots"]["TestBot"]

    symlink_path = tmp_path / "orchestrator_link"
    try:
        os.symlink(manager.base_dir, symlink_path)
    except OSError:
        pytest.skip("Symlinks are not supported on this environment")

    with patch.object(manager, "_sync_bot_from_archive", return_value=True) as sync_mock:
        manager._update_bot_from_repo("TestBot", bot_config, str(symlink_path))

    sync_mock.assert_not_called()
