# Bot Orchestrator

Central manager for starting, stopping, restarting and monitoring multiple bot subprocesses (example: Discord bots).

Quickstart

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

2. Run the manager (example):

```bash
# start all bots configured in bot_config.yaml
python main.py start_all

# start a single bot
python main.py start ARKBots
```

3. Issue commands via `bot_commands.txt` by appending lines such as `restart ARKBots`.

Notes
- `bot_config.yaml` defines bots and directories.
- Example bots are in `examples/` so you can run the manager locally without real tokens.
- The manager persists state in `bot_states.db` and writes logs to `logs/`.

Environment
- Provide any bot-specific secrets via environment variables (see `.env.example`).

License
- This project is provided under the MIT license. See `LICENSE`.
