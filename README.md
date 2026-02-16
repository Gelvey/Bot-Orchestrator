# Bot Orchestrator

Single-process manager for starting, stopping, and monitoring multiple Python bot subprocesses.

## Features

- Start, stop, restart, pause, and resume individual bots
- Restore previously-running bots on startup (`start_all`)
- Persist state in SQLite (`bot_states.db`)
- Poll and execute runtime commands from `bot_commands.txt`
- Stream bot stdout/stderr with per-bot color prefixes
- Optional per-bot Git auto-update with safety checks

## Repository Files

- `main.py`: Orchestrator entrypoint and `BotManager`
- `bot_config.yaml`: Active runtime configuration (required at runtime)
- `bot_config-example.yaml`: Template you should copy from
- `bot_commands.txt`: Runtime command queue file (auto-created if missing)
- `bot_states.db`: SQLite state database (auto-created)
- `logs/bot_manager.log`: Manager log file (auto-created)
- `examples/*/main.py`: Minimal bot examples

## Quick Start

1. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. Create runtime config:

```bash
cp bot_config-example.yaml bot_config.yaml
```

3. Start manager:

```bash
python main.py start_all
```

## CLI Usage

```bash
python main.py start_all
python main.py start <BotName>
python main.py stop <BotName>
python main.py restart <BotName>
python main.py pause <BotName>
python main.py resume <BotName>
python main.py status <BotName>
python main.py list
```

## Runtime Command File

While `start_all` is running, the manager polls `bot_commands.txt` every 2 seconds and executes commands.

Supported command actions:

- `start <BotName>`
- `stop <BotName>`
- `restart <BotName>`
- `pause <BotName>`
- `resume <BotName>`
- `status_all <anything>` (second token is currently required by parser)

Examples:

```bash
echo "restart Task-Master" >> bot_commands.txt
echo "pause DataBot" >> bot_commands.txt
echo "resume DataBot" >> bot_commands.txt
echo "status_all now" >> bot_commands.txt
```

## Configuration Reference (`bot_config.yaml`)

Top-level structure:

```yaml
bots:
	<BotName>:
		script: main.py
		directory: path/to/bot
		color: cyan
		description: Optional human-readable description
		repo_url: https://github.com/owner/repo.git
		auto_update: true
		force_sync: false
		preserve_files:
			- .env
			- config/local.yaml

global_settings:
	log_directory: logs
	max_restart_attempts: 3
	restart_delay: 5
```

### Per-bot keys

- `script` (required): Python entrypoint relative to `directory`
- `directory` (required): Bot working directory. Relative paths resolve from the orchestrator directory.
- `color` (optional): Console prefix color (`red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`)
- `description` (optional): Informational text only
- `repo_url` (optional): Enables Git auto-update behavior when present
- `auto_update` (optional, default `true` if `repo_url` exists): Toggle auto-update
- `force_sync` (optional, default `false`): If local git changes exist, force-sync with remote instead of skipping update
- `preserve_files` (optional): List of relative files/directories to restore after force-sync

### Auto-update behavior

When enabled, update flow is:

1. Verify directory exists
2. Verify the directory is in a git repo (or bootstrap git metadata)
3. Check working tree cleanliness
4. Verify `origin` matches `repo_url`
5. Run `git pull --ff-only`

If local changes are detected:

- `force_sync: false` -> update is skipped
- `force_sync: true` -> manager:
	- backs up each path in `preserve_files`
	- runs fetch + hard reset to remote default branch
	- restores backed-up files/directories

### `preserve_files` rules

- Paths must be relative to the bot `directory`
- Entries outside the bot directory are rejected
- Missing files are ignored
- Paths are exact entries (file or directory), not wildcard patterns

## State Persistence

`bot_states.db` stores per-bot lifecycle data:

- `is_running`
- `start_count`
- `last_start_time`
- `preserved_state` (used for restore-on-next-start behavior)

## Logging

- Console logs + `logs/bot_manager.log`
- Bot output is streamed with `[BotName]` prefixes and configured color

## Development & Testing

```bash
pip install -r requirements-dev.txt
pytest -q
```

Note: tests in `tests/test_config_and_files.py` expect root files `bot_config.yaml` and `bot_commands.txt`.

## License

MIT. See `LICENSE`.
