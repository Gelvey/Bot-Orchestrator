# Bot Orchestrator

Central manager for starting, stopping, restarting and monitoring multiple bot subprocesses (example: Discord bots).

## Features

- **Process Management**: Start, stop, restart, and monitor multiple bot processes
- **State Persistence**: SQLite database tracks bot states and restores them after restart
- **Graceful Shutdown**: Preserves bot states and handles SIGINT/SIGTERM signals
- **Colorized Output**: Console output prefixed with bot name in configurable colors
- **Command Interface**: Dynamic control via `bot_commands.txt` file
- **Logging**: Dual output to file and console with automatic log directory creation

## Quick Start

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. Run the manager (example):

```bash
# Start all bots configured in bot_config.yaml
python main.py start_all

# Start a single bot
python main.py start ARKBots

# Stop a bot
python main.py stop ARKBots

# Restart a bot
python main.py restart ARKBots

# List all bots and their states
python main.py list

# Check status of a specific bot
python main.py status ARKBots
```

3. Issue commands dynamically via `bot_commands.txt` by appending lines:

```bash
echo "restart ARKBots" >> bot_commands.txt
echo "start NeuroBot" >> bot_commands.txt
echo "status_all" >> bot_commands.txt
```

## Configuration

- **`bot_config.yaml`**: Defines bots, their directories, scripts, and console colors
- **`bot_commands.txt`**: Runtime command interface (automatically created)
- **`.env.example`**: Template for bot-specific environment variables
- **Example bots**: Located in `examples/` directory for local testing without real tokens

## State Persistence

The manager persists bot states in `bot_states.db` (SQLite) including:
- Running status
- Start count
- Last start time
- Preserved state for automatic restoration

## Logging

Logs are written to `logs/bot_manager.log` and displayed in the console with colorized output per bot.

## Development

Install development dependencies for testing:

```bash
pip install -r requirements-dev.txt
pytest
```

## Environment Variables

Provide bot-specific secrets via environment variables (see `.env.example`):
- `DISCORD_TOKEN_<BOT_NAME>`: Discord API token for each bot
- Additional variables as needed by individual bots

## License

This project is provided under the MIT license. See `LICENSE`.
