# stdin/stdout Integration for Docker Panels

## Overview

The Bot Orchestrator now supports stdin/stdout command processing, enabling integration with Docker game panel systems like Pterodactyl and Pelican.dev. These panels use WebSocket connections to provide real-time console interaction with containerized applications.

## How It Works

### Architecture

1. **Panel Browser UI** → WebSocket → **Panel Backend** → **Wings/Container Runtime** → **stdin of orchestrator**
2. **stdout of orchestrator** → **Wings/Container Runtime** → **Panel Backend** → WebSocket → **Panel Browser UI**

### Implementation Details

- **stdin listener thread**: Continuously reads commands from stdin
- **Command processing**: Uses the same command execution logic as file-based commands
- **stdout responses**: Structured output format `[ORCHESTRATOR] <command>: <status> - <message>`
- **Dual mode**: Both file-based (`bot_commands.txt`) and stdin commands work simultaneously

## Configuration

### Enable stdin Mode

Add to your `bot_config.yaml`:

```yaml
global_settings:
  stdin_mode: true  # Enable stdin/stdout command interface
```

### Supported Commands

All standard orchestrator commands work via stdin:

- `start <BotName>` - Start a bot
- `stop <BotName>` - Stop a bot
- `restart <BotName>` - Restart a bot
- `pause <BotName>` - Pause a bot
- `resume <BotName>` - Resume a bot
- `status <BotName>` - Get bot status
- `list` - List all bots

## Usage Examples

### Interactive Mode

```bash
python main.py start_all
# Then type commands:
list
start HelperBot
status HelperBot
```

### Piped Commands

```bash
echo "list" | python main.py start_all
echo "start HelperBot" | python main.py start_all
```

### Docker Panel Integration

When running in a Docker container with panel integration:

1. Panel user types command in web console
2. Panel sends command via WebSocket to Wings
3. Wings writes to container's stdin
4. Orchestrator reads from stdin, processes command
5. Orchestrator writes response to stdout
6. Wings captures stdout, sends via WebSocket to panel
7. Panel displays response in web console

## Response Format

All stdin commands produce structured responses:

```
[ORCHESTRATOR] <command>: <STATUS> - <message>
```

Examples:
```
[ORCHESTRATOR] start HelperBot: SUCCESS - Bot HelperBot started
[ORCHESTRATOR] status HelperBot: SUCCESS - Bot HelperBot is running. Previously Running
[ORCHESTRATOR] stop NonExistent: FAILED - Bot NonExistent not found in configuration
```

## Testing

Run the test suite:

```bash
pytest tests/test_stdin_mode.py -v
```

All tests:

```bash
pytest tests/ -v
```

## Benefits

✅ **Real-time control**: Commands execute immediately via stdin
✅ **Panel compatibility**: Works with Pterodactyl, Pelican.dev, and similar systems
✅ **Backward compatible**: File-based commands still work
✅ **Structured output**: Easy to parse responses in panel UI
✅ **No polling delay**: Instant command execution (unlike 2-second file polling)

## Technical Notes

- stdin processing runs in a separate daemon thread
- Thread stops gracefully on shutdown or stdin EOF
- Both stdin and file-based command processing can run simultaneously
- stdin mode is opt-in via configuration (disabled by default)
- All command execution logic is shared between stdin and file modes

## Demo

Run the demo script:

```bash
./demo_stdin.sh
```

This shows example usage and output format.
