# Bot Orchestrator

Single-process manager for starting, stopping, and monitoring multiple Python bot subprocesses.

## Features

- Start, stop, restart, pause, and resume individual bots
- Restore previously-running bots on startup (`start_all`)
- Persist state in SQLite (`bot_states.db`)
- Poll and execute runtime commands from `bot_commands.txt`
- **stdin/stdout command interface** for Docker panel integration (Pterodactyl, Pelican.dev)
- Stream bot stdout/stderr with per-bot color prefixes
- Optional per-bot Git auto-update with safety checks

## Repository Files

- `main.py`: Orchestrator entrypoint and `BotManager`
- `bot_config.yaml`: Active runtime configuration (required at runtime, intentionally untracked)
- `bot_config-example.yaml`: Template you should copy from
- `bot_commands.txt`: Runtime command queue file (auto-created if missing)
- `bot_states.db`: SQLite state database (auto-created)
- `logs/bot_manager.log`: Manager log file (auto-created)
- `examples/*/main.py`: Minimal bot examples
- `STDIN_INTEGRATION.md`: Detailed stdin/stdout integration guide for Docker panels
- `demo_stdin.sh`: Interactive demo script for stdin mode

Note: `bot_config.yaml` is a local runtime file and should not be committed.

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
`bot_commands.txt` is intentionally plain (usually empty between polls); command format and examples are documented here.

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

## stdin/stdout Command Interface

**For Docker panel integration** (Pterodactyl, Pelican.dev, etc.)

Enable `stdin_mode` in `global_settings` to process commands from stdin and output responses to stdout. This allows real-time WebSocket-based console interaction in game panel UIs.

### How it works

When `stdin_mode: true` is configured:

- ✅ Orchestrator listens for commands on stdin
- ✅ Commands execute instantly (no polling delay)
- ✅ Responses written to stdout: `[ORCHESTRATOR] <command>: <status> - <message>`
- ✅ File-based commands (`bot_commands.txt`) still work simultaneously

### Supported Commands

All standard commands work via stdin:

```
start <BotName>       Start a bot
stop <BotName>        Stop a bot
restart <BotName>     Restart a bot
pause <BotName>       Pause (suspend) a bot
resume <BotName>      Resume a paused bot
status <BotName>      Get bot status
list                  List all bots
```

### Usage Example

Start orchestrator with stdin mode enabled:

```bash
python main.py start_all
```

Send commands (interactively or via WebSocket):

```bash
start HelperBot
status HelperBot
list
stop HelperBot
```

### Response Format

```
[ORCHESTRATOR] start HelperBot: SUCCESS - Bot HelperBot started
[ORCHESTRATOR] status HelperBot: SUCCESS - Bot HelperBot is running. Previously Running
[ORCHESTRATOR] stop HelperBot: SUCCESS - Bot HelperBot stopped
[ORCHESTRATOR] list: SUCCESS - Listed all bots
```

> **📖 See [STDIN_INTEGRATION.md](STDIN_INTEGRATION.md) for detailed integration guide**
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
		repo_branch: main
		auto_update: true
		force_sync: false
		preserve_files:
			- .env
			- config/local.yaml

global_settings:
	suppress_discord_messages: false
	stdin_mode: false
	log_directory: logs
	max_restart_attempts: 3
	restart_delay: 5
```

### Per-bot keys

- `script` (required): Python entrypoint relative to `directory`
- `directory` (required): Bot working directory. Relative paths resolve from the orchestrator directory.
- `color` (optional): Console prefix color (`red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`)
- `description` (optional): Informational text only
- `repo_url` (optional): Enables archive-based auto-update behavior when present
- `repo_branch` (optional): Preferred branch name for archive downloads (fallback order is configured branch, then `main`, then `master`)
- `auto_update` (optional, default `true` if `repo_url` exists): Toggle auto-update
- `force_sync` (optional, default `false`): Replace directory contents with archive contents; when `false`, archive files are merged into existing directory
- `preserve_files` (optional): List of relative files/directories to restore after force-sync

### Global settings keys

- `suppress_discord_messages` (optional, default `false`): Suppress bot output lines that contain both `discord` and `message` for all bots
- `stdin_mode` (optional, default `false`): Enable stdin/stdout command interface for Docker panel integration (Pterodactyl, Pelican.dev). When enabled, commands from stdin are processed and responses are written to stdout
- `log_directory` (optional): Log directory name
- `max_restart_attempts` (optional): Reserved for restart policy
- `restart_delay` (optional): Reserved for restart policy delay in seconds

### Auto-update behavior

When enabled, update flow is:

1. Verify directory exists
2. Validate update target does not overlap orchestrator root path
3. Build GitHub codeload archive URL from `repo_url`
4. Download and extract branch archive
5. Sync extracted files into bot directory

If `force_sync: true`, manager clears directory contents before sync. In both modes, configured `preserve_files` entries are backed up and restored after sync.

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
- With `global_settings.suppress_discord_messages: true`, Discord message lines are hidden from console output for all bots

## Development & Testing

```bash
pip install -r requirements-dev.txt
pytest -q
```

Note: tests in `tests/test_config_and_files.py` expect root files `bot_config.yaml` and `bot_commands.txt`.

## License

MIT. See `LICENSE`.
