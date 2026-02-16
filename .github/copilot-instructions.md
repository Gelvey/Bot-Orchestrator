# Copilot Instructions for Bot-Orchestrator

## Project focus
- This repo is a single-process orchestrator for multiple Python bot subprocesses (`main.py`, class `BotManager`).
- Runtime behavior centers on three local artifacts in repo root: `bot_config.yaml`, `bot_commands.txt`, and `bot_states.db`.
- Example bot entrypoints live in `examples/` and are intentionally minimal (`examples/*/main.py`).

## Architecture and data flow
- `BotManager` loads YAML config, validates `bots.*.script` and `bots.*.directory`, and resolves paths relative to the orchestrator file’s directory (`main.py`).
- Bot processes are launched with `subprocess.Popen([sys.executable, script_path], ...)`; keep Python-executable consistency when changing launch logic.
- State persistence is SQLite (`bot_states` table in `bot_states.db`) with `is_running`, `start_count`, `last_start_time`, `preserved_state`.
- On SIGINT/SIGTERM, the manager preserves running state first, then stops child processes and exits.
- Dynamic control uses polling of `bot_commands.txt` every 2 seconds (`COMMAND_CHECK_INTERVAL`).

## Concurrency and lifecycle conventions
- `self.processes` is shared mutable state; keep all reads/writes guarded by `self.lock` as in `start_bot`, `stop_bot`, and `_stream_output`.
- Output streaming is thread-based and color-prefixed per bot; preserve this behavior when touching stdout/stderr handling.
- Shutdown semantics matter: `start_all_bots()` restores only bots marked previously running.

## Git auto-update behavior
- Auto-update is per-bot config (`repo_url`, optional `auto_update`, default enabled when `repo_url` exists).
- `_update_bot_from_repo` intentionally skips update when:
  - working tree is dirty,
  - directory is not a git repo,
  - `origin` URL does not match configured `repo_url`.
- Keep `git pull --ff-only` safety behavior unless explicitly changing update policy.

## Developer workflows
- Run orchestrator: `python main.py start_all`, `python main.py start <BotName>`, `python main.py stop <BotName>`, `python main.py list`, `python main.py status <BotName>`.
- Tests: `pytest` or targeted `pytest tests/test_github_auto_update.py -q`.
- Tests in `tests/test_config_and_files.py` expect root files `bot_config.yaml` and `bot_commands.txt` to exist.

## Project-specific editing guidance
- Prefer minimal, surgical edits in `main.py`; most functionality is centralized there.
- When changing config shape, update both validation (`_load_config`) and sample config (`bot_config-example.yaml`).
- Preserve existing CLI action names and command-file action strings (`start|stop|restart|pause|resume`).
- Use existing logging style (`self.logger.<level>`) and avoid introducing parallel logging mechanisms.
