import os
import subprocess
import sys
import threading
import signal
import time
import argparse
import logging
import yaml
import sqlite3
import shutil
import tempfile
from typing import Dict, List, Optional, Tuple
from threading import Event
from contextlib import closing
import queue

# Constants
COMMAND_CHECK_INTERVAL = 2  # seconds
PROCESS_STOP_TIMEOUT = 10  # seconds
PROCESS_FORCE_KILL_TIMEOUT = 15  # seconds
DEFAULT_LOG_LEVEL = logging.INFO
GIT_COMMAND_TIMEOUT = 30  # seconds

class BotManager:
    """
    Manages multiple bot subprocesses with state persistence and graceful shutdown.
    
    Features:
    - Start, stop, restart, and monitor bot processes
    - Persist bot states in SQLite database
    - Colorized console output per bot
    - Command file interface for dynamic control
    - Automatic state restoration on startup
    - Graceful shutdown with state preservation
    """
    
    def __init__(self, config_path: str = 'bot_config.yaml', commands_file: str = 'bot_commands.txt', db_path: str = 'bot_states.db'):
        """
        Initialize the BotManager.
        
        Args:
            config_path: Path to YAML configuration file
            commands_file: Path to file for runtime commands
            db_path: Path to SQLite database for state persistence
        """
        # Use absolute path for config and base directory
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.base_dir, config_path)
        self.commands_file_path = os.path.join(self.base_dir, commands_file)
        self.db_path = os.path.join(self.base_dir, db_path)
        
        # Bot process tracking
        self.processes: Dict[str, Dict] = {}
        
        self.logger = self._setup_logging()
        self.config = self._load_config()
        self.lock = threading.Lock()
        self.shutdown_event = Event()
        self.command_queue = queue.Queue()
        
        self.COLORS = {
            'reset': '\033[0m',
            'red': '\033[91m',
            'green': '\033[92m',
            'yellow': '\033[93m',
            'blue': '\033[94m',
            'magenta': '\033[95m',
            'cyan': '\033[96m',
            'white': '\033[97m',
        }
        
        # Ensure commands file exists
        self._ensure_commands_file_exists()
        
        # Setup database
        self._setup_database()
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _setup_logging(self) -> logging.Logger:
        """
        Set up logging to both file and console.
        
        Returns:
            Configured logger instance for BotManager
        """
        log_dir = os.path.join(self.base_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        logging.basicConfig(
            level=DEFAULT_LOG_LEVEL,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(log_dir, 'bot_manager.log')),
                logging.StreamHandler(sys.stdout)
            ]
        )
        return logging.getLogger('BotManager')

    def _ensure_commands_file_exists(self, log_if_created: bool = False) -> bool:
        """
        Ensure command file and its parent directory exist.

        Args:
            log_if_created: Whether to emit a warning when the file is recreated

        Returns:
            True when file exists or was created successfully, False otherwise
        """
        try:
            commands_dir = os.path.dirname(self.commands_file_path)
            if commands_dir:
                os.makedirs(commands_dir, exist_ok=True)

            if not os.path.exists(self.commands_file_path):
                with open(self.commands_file_path, 'w') as f:
                    f.write('# Commands will be appended here by users or other systems\n')
                    f.write('# Example: start ARKBots\n')

                if log_if_created:
                    self.logger.warning(f"Recreated missing command file: {self.commands_file_path}")

            return True
        except Exception as e:
            self.logger.error(f"Failed to ensure command file exists at {self.commands_file_path}: {e}")
            return False

    def _setup_database(self):
        """
        Set up SQLite database for tracking bot states
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_states (
                    bot_name TEXT PRIMARY KEY,
                    is_running INTEGER DEFAULT 0,
                    last_start_time DATETIME,
                    start_count INTEGER DEFAULT 0,
                    preserved_state INTEGER DEFAULT 0
                )
            ''')
            conn.commit()

    def _save_bot_state(self, bot_name: str, is_running: bool, preserved_state: Optional[bool] = None):
        """
        Save bot state to database.
        
        Args:
            bot_name: Name of the bot
            is_running: Whether bot is currently running
            preserved_state: Optional flag to mark bot for restoration on restart
        """
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # If preserved_state is explicitly passed, update it, otherwise keep existing value
                if preserved_state is not None:
                    cursor.execute('''
                        INSERT INTO bot_states (bot_name, is_running, last_start_time, start_count, preserved_state) 
                        VALUES (?, ?, datetime('now'), 1, ?)
                        ON CONFLICT(bot_name) DO UPDATE SET 
                        is_running = ?, 
                        last_start_time = datetime('now'),
                        start_count = start_count + 1,
                        preserved_state = ?
                    ''', (bot_name, int(is_running), int(preserved_state), int(is_running), int(preserved_state)))
                else:
                    cursor.execute('''
                        INSERT INTO bot_states (bot_name, is_running, last_start_time, start_count) 
                        VALUES (?, ?, datetime('now'), 1)
                        ON CONFLICT(bot_name) DO UPDATE SET 
                        is_running = ?, 
                        last_start_time = datetime('now'),
                        start_count = start_count + 1
                    ''', (bot_name, int(is_running), int(is_running)))
                
                conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to save state for {bot_name}: {e}")

    def _get_bot_saved_state(self, bot_name: str) -> bool:
        """
        Retrieve bot's saved state from database.
        
        Args:
            bot_name: Name of the bot to check
            
        Returns:
            True if bot was running before shutdown, False otherwise
        """
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT is_running, preserved_state FROM bot_states WHERE bot_name = ?', (bot_name,))
                result = cursor.fetchone()
                
                if not result:
                    return False
                
                # Check preserved_state first (tracks if bot was running before shutdown)
                # Then fall back to is_running
                return result[1] == 1 if result[1] is not None else (result[0] == 1)
        except Exception as e:
            self.logger.error(f"Failed to retrieve state for {bot_name}: {e}")
            return False

    def _load_config(self) -> Dict:
        """
        Load and validate bot configuration from YAML file.
        
        Returns:
            Dictionary containing bot configurations
            
        Raises:
            SystemExit: If configuration is invalid
        """
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            if not isinstance(config, dict) or 'bots' not in config:
                raise ValueError("Invalid configuration format: missing 'bots' section")
            
            # Validate bot configurations
            for bot_name, bot_config in config['bots'].items():
                if 'script' not in bot_config or 'directory' not in bot_config:
                    raise ValueError(f"Bot '{bot_name}' is missing required fields (script, directory)")
            
            self.logger.info(f"Loaded configuration for {len(config['bots'])} bots")
            return config
        except FileNotFoundError:
            self.logger.warning(f"Config file {self.config_path} not found. Creating default.")
            default_config = {
                'bots': {
                    'ARKBots': {'script': 'main.py', 'color': 'green', 'directory': 'ARKBots'},
                    'NeuroBeam': {'script': 'app.py', 'color': 'cyan', 'directory': 'NeuroBeam'},
                    'NeuroBot': {'script': 'new-NeuroBot.py', 'color': 'yellow', 'directory': 'NeuroBot'},
                    'NeuroTickets': {'script': 'main.py', 'color': 'magenta', 'directory': 'NeuroTickets'}
                }
            }
            with open(self.config_path, 'w') as f:
                yaml.dump(default_config, f)
            return default_config
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            sys.exit(1)

    def _handle_exit(self, signum=None, frame=None):
        """
        Handle SIGINT or SIGTERM signals to gracefully shut down the bot manager.
        Improved to preserve the running state of bots before shutdown.
        """
        try:
            # Prevent multiple simultaneous shutdown attempts
            if self.shutdown_event.is_set():
                return

            self.logger.info("Initiating graceful shutdown...")
            
            # First, preserve the state of all running bots
            with self.lock:
                for bot_name in self.processes.keys():
                    # Mark this bot as preserved (should be restarted on next launch)
                    self._save_bot_state(bot_name, True, True)
                    self.logger.info(f"Preserved running state for {bot_name}")
            
            # Set the shutdown event to signal all threads
            self.shutdown_event.set()

            # Create a stop command queue to ensure thread-safe bot stopping
            stop_queue = []
            with self.lock:
                stop_queue = list(self.processes.keys())

            # Stop bots in parallel
            stop_threads = []
            for bot_name in stop_queue:
                stop_thread = threading.Thread(
                    target=self._parallel_stop_bot, 
                    args=(bot_name, False),  # Pass False to prevent state update
                    daemon=True
                )
                stop_thread.start()
                stop_threads.append(stop_thread)

            # Wait for stop threads with a timeout
            for thread in stop_threads:
                thread.join(timeout=PROCESS_STOP_TIMEOUT)

            # Force terminate any remaining processes
            with self.lock:
                for bot_name, bot_info in list(self.processes.items()):
                    try:
                        bot_info['process'].kill()
                    except Exception as e:
                        self.logger.warning(f"Failed to kill {bot_name}: {e}")

            # Close database connections
            self._close_database_connections()

            self.logger.info("Shutdown complete.")
            sys.exit(0)

        except Exception as final_error:
            self.logger.error(f"Fatal error during shutdown: {final_error}")
            sys.exit(1)

    def _parallel_stop_bot(self, bot_name: str, update_state: bool = True):
        """
        Thread-safe method to stop a bot with a timeout
        """
        try:
            # Attempt graceful termination
            with self.lock:
                if bot_name not in self.processes:
                    return

                bot_info = self.processes[bot_name]
                process = bot_info['process']

            self.logger.info(f"Attempting to stop {bot_name} (PID {process.pid})...")
            
            # Send SIGTERM first to allow bot to perform cleanup
            process.terminate()

            try:
                # Wait for process to exit gracefully
                process.wait(timeout=PROCESS_STOP_TIMEOUT)
                self.logger.info(f"{bot_name} exited gracefully.")
            except subprocess.TimeoutExpired:
                # Send SIGKILL if process doesn't exit
                self.logger.warning(f"{bot_name} did not exit in time. Forcing termination...")
                process.kill()

            # Ensure state is saved before removing from processes, 
            # but only if update_state is True (we don't update during shutdown)
            if update_state:
                self._save_bot_state(bot_name, False, False)

            # Clean up process references
            with self.lock:
                if bot_name in self.processes:
                    del self.processes[bot_name]

        except Exception as e:
            self.logger.error(f"Error stopping {bot_name}: {e}")

    def start_all_bots(self):
        """
        Start all configured bots based on their saved states
        """
        # Check and update database schema if needed
        self._ensure_preserved_state_column()
        
        started_bots = []
        for bot_name in self.config['bots'].keys():
            # Check if bot was previously running (using preserved state)
            if self._get_bot_saved_state(bot_name):
                if self.start_bot(bot_name):
                    started_bots.append(bot_name)
                    # Reset preserved state after starting
                    self._save_bot_state(bot_name, True, False)
        
        print("\n" + "=" * 60)
        print(f"Started {len(started_bots)} bots: {', '.join(started_bots)}")
        print("=" * 60)

        # Start command file monitoring thread
        command_thread = threading.Thread(
            target=self._process_command_file, 
            daemon=True
        )
        command_thread.start()

        # Keep main thread running with improved interruption handling
        try:
            while not self.shutdown_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            self._handle_exit()

    def _ensure_preserved_state_column(self):
        """
        Ensure the preserved_state column exists in the database
        """
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Check if preserved_state column exists
                cursor.execute("PRAGMA table_info(bot_states)")
                columns = cursor.fetchall()
                column_names = [col[1] for col in columns]
                
                if 'preserved_state' not in column_names:
                    self.logger.info("Adding preserved_state column to bot_states table")
                    cursor.execute("ALTER TABLE bot_states ADD COLUMN preserved_state INTEGER DEFAULT 0")
                    conn.commit()
        except Exception as e:
            self.logger.error(f"Error ensuring preserved_state column: {e}")

    def _close_database_connections(self):
        """
        Safely close database connections
        """
        try:
            # Use a separate connection to avoid any lingering connections
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.close()
        except Exception as e:
            self.logger.error(f"Error closing database connections: {e}")

    def _should_auto_update_bot(self, bot_config: Dict) -> bool:
        """
        Determine if GitHub auto-update should run for a bot.
        Returns True only when repo_url is configured and auto_update is not False
        (defaults to True when repo_url exists).
        """
        repo_url = bot_config.get('repo_url')
        if not repo_url:
            return False
        return bot_config.get('auto_update', True)

    def _should_force_sync_bot(self, bot_config: Dict) -> bool:
        """
        Determine if auto-update should force synchronization when local
        changes are present.
        """
        return bool(bot_config.get('force_sync', False))

    def _is_safe_auto_update_target(self, directory: str) -> bool:
        """
        Ensure auto-update target is not the orchestrator directory itself
        or one of its parent directories.
        """
        base_dir_abs = os.path.realpath(os.path.abspath(self.base_dir))
        target_abs = os.path.realpath(os.path.abspath(directory))

        if target_abs == base_dir_abs:
            return False

        if base_dir_abs.startswith(target_abs + os.sep):
            return False

        return True

    def _get_preserve_files(self, bot_config: Dict) -> List[str]:
        """
        Return a list of relative file paths that should be preserved across
        forced git synchronization.
        """
        preserve_files = bot_config.get('preserve_files', [])
        if not isinstance(preserve_files, list):
            self.logger.warning("Invalid preserve_files value in bot config; expected a list")
            return []

        normalized_paths: List[str] = []
        for preserve_path in preserve_files:
            if isinstance(preserve_path, str) and preserve_path.strip():
                normalized_paths.append(preserve_path.strip())
        return normalized_paths

    def _resolve_remote_target_ref(self, directory: str) -> Optional[str]:
        """
        Resolve the best remote target ref for hard reset.
        """
        head_result = subprocess.run(
            ['git', 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD'],
            cwd=directory,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_COMMAND_TIMEOUT
        )

        if head_result.returncode == 0:
            head_ref = head_result.stdout.strip()
            if head_ref.startswith('origin/'):
                return head_ref

        for fallback_branch in ('origin/main', 'origin/master'):
            branch_check = subprocess.run(
                ['git', 'show-ref', '--verify', '--quiet', f'refs/remotes/{fallback_branch}'],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_COMMAND_TIMEOUT
            )
            if branch_check.returncode == 0:
                return fallback_branch

        return None

    def _force_sync_bot_repo(self, bot_name: str, directory: str, repo_url: str, preserve_files: List[str]) -> bool:
        """
        Force-sync repository to the remote default branch while preserving
        configured local files.
        """
        backup_dir = tempfile.mkdtemp(prefix=f"bot-preserve-{bot_name}-")
        preserved_entries: List[Tuple[str, str, bool]] = []

        try:
            directory_abs = os.path.abspath(directory)

            for relative_path in preserve_files:
                source_path = os.path.abspath(os.path.join(directory_abs, relative_path))
                if source_path != directory_abs and not source_path.startswith(directory_abs + os.sep):
                    self.logger.warning(
                        f"Preserve file skipped for {bot_name}: {relative_path} is outside bot directory"
                    )
                    continue

                if not os.path.exists(source_path):
                    continue

                backup_path = os.path.join(backup_dir, relative_path)
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)

                if os.path.isdir(source_path):
                    shutil.copytree(source_path, backup_path, dirs_exist_ok=True)
                    preserved_entries.append((relative_path, backup_path, True))
                else:
                    shutil.copy2(source_path, backup_path)
                    preserved_entries.append((relative_path, backup_path, False))

            remote_result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_COMMAND_TIMEOUT
            )

            if remote_result.returncode != 0:
                add_remote_result = subprocess.run(
                    ['git', 'remote', 'add', 'origin', repo_url],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=GIT_COMMAND_TIMEOUT
                )
                if add_remote_result.returncode != 0:
                    self.logger.warning(
                        f"Force sync failed for {bot_name}: unable to add origin "
                        f"({add_remote_result.stderr.strip()})"
                    )
                    return False
            elif remote_result.stdout.strip() != repo_url:
                set_remote_result = subprocess.run(
                    ['git', 'remote', 'set-url', 'origin', repo_url],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=GIT_COMMAND_TIMEOUT
                )
                if set_remote_result.returncode != 0:
                    self.logger.warning(
                        f"Force sync failed for {bot_name}: unable to set origin URL "
                        f"({set_remote_result.stderr.strip()})"
                    )
                    return False

            fetch_result = subprocess.run(
                ['git', 'fetch', 'origin'],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_COMMAND_TIMEOUT
            )
            if fetch_result.returncode != 0:
                self.logger.warning(
                    f"Force sync failed for {bot_name}: git fetch failed ({fetch_result.stderr.strip()})"
                )
                return False

            target_ref = self._resolve_remote_target_ref(directory)
            if not target_ref:
                self.logger.warning(f"Force sync failed for {bot_name}: unable to resolve remote default branch")
                return False

            reset_result = subprocess.run(
                ['git', 'reset', '--hard', target_ref],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_COMMAND_TIMEOUT
            )
            if reset_result.returncode != 0:
                self.logger.warning(
                    f"Force sync failed for {bot_name}: git reset failed ({reset_result.stderr.strip()})"
                )
                return False

            for relative_path, backup_path, is_dir in preserved_entries:
                destination = os.path.join(directory_abs, relative_path)
                os.makedirs(os.path.dirname(destination), exist_ok=True)

                if is_dir:
                    if os.path.exists(destination):
                        shutil.rmtree(destination)
                    shutil.copytree(backup_path, destination)
                else:
                    shutil.copy2(backup_path, destination)

            self.logger.info(
                f"Force sync completed for {bot_name} ({len(preserved_entries)} preserved path(s))"
            )
            return True
        finally:
            shutil.rmtree(backup_dir, ignore_errors=True)

    def _attempt_git_bootstrap(self, bot_name: str, directory: str, repo_url: str) -> bool:
        """
        Attempt to bootstrap git metadata for a bot directory when code exists
        but repository metadata is missing.
        """
        self.logger.info(f"Auto-update bootstrap for {bot_name}: initializing git metadata in {directory}")

        init_result = subprocess.run(
            ['git', 'init'],
            cwd=directory,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_COMMAND_TIMEOUT
        )
        if init_result.returncode != 0:
            self.logger.warning(
                f"Auto-update bootstrap failed for {bot_name}: git init failed ({init_result.stderr.strip()})"
            )
            return False

        add_remote_result = subprocess.run(
            ['git', 'remote', 'add', 'origin', repo_url],
            cwd=directory,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_COMMAND_TIMEOUT
        )
        if add_remote_result.returncode != 0:
            set_remote_result = subprocess.run(
                ['git', 'remote', 'set-url', 'origin', repo_url],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_COMMAND_TIMEOUT
            )
            if set_remote_result.returncode != 0:
                self.logger.warning(
                    f"Auto-update bootstrap failed for {bot_name}: unable to configure origin remote "
                    f"({set_remote_result.stderr.strip() or add_remote_result.stderr.strip()})"
                )
                return False

        fetch_result = subprocess.run(
            ['git', 'fetch', 'origin'],
            cwd=directory,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_COMMAND_TIMEOUT
        )
        if fetch_result.returncode != 0:
            self.logger.warning(
                f"Auto-update bootstrap failed for {bot_name}: git fetch failed ({fetch_result.stderr.strip()})"
            )
            return False

        target_ref = self._resolve_remote_target_ref(directory)
        if not target_ref:
            self.logger.warning(f"Auto-update bootstrap failed for {bot_name}: unable to resolve remote default branch")
            return False

        reset_result = subprocess.run(
            ['git', 'reset', '--hard', target_ref],
            cwd=directory,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_COMMAND_TIMEOUT
        )
        if reset_result.returncode == 0:
            self.logger.info(f"Auto-update bootstrap completed for {bot_name} using {target_ref}")
            return True

        self.logger.warning(
            f"Auto-update bootstrap failed for {bot_name}: git reset failed ({reset_result.stderr.strip()})"
        )
        return False

    def _update_bot_from_repo(self, bot_name: str, bot_config: Dict, directory: str):
        """
        Optionally update bot code from configured GitHub repository.
        Validates git repo state (clean working tree, origin URL match) and uses
        `git pull --ff-only` to avoid unintended overwrites.
        """
        if not self._should_auto_update_bot(bot_config):
            return

        repo_url = bot_config.get('repo_url')
        if not isinstance(repo_url, str) or not repo_url.strip():
            return
        repo_url = repo_url.strip()

        if not os.path.isdir(directory):
            self.logger.warning(f"Auto-update skipped for {bot_name}: directory {directory} not found")
            return

        if not self._is_safe_auto_update_target(directory):
            self.logger.warning(
                f"Auto-update skipped for {bot_name}: unsafe update target {directory} overlaps orchestrator path"
            )
            return

        try:
            repo_check_result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_COMMAND_TIMEOUT
            )
            if repo_check_result.returncode != 0:
                if not self._attempt_git_bootstrap(bot_name, directory, repo_url):
                    reason = repo_check_result.stderr.strip() or f"{directory} is not in a git repository"
                    self.logger.warning(f"Auto-update skipped for {bot_name}: {reason}")
                    return

                repo_check_result = subprocess.run(
                    ['git', 'rev-parse', '--show-toplevel'],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=GIT_COMMAND_TIMEOUT
                )
                if repo_check_result.returncode != 0:
                    reason = repo_check_result.stderr.strip() or f"{directory} is not in a git repository"
                    self.logger.warning(f"Auto-update skipped for {bot_name}: {reason}")
                    return

            status_result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_COMMAND_TIMEOUT
            )
            if status_result.returncode != 0:
                self.logger.warning(
                    f"Auto-update skipped for {bot_name}: unable to check git status ({status_result.stderr.strip()})"
                )
                return

            if status_result.stdout.strip():
                if self._should_force_sync_bot(bot_config):
                    preserve_files = self._get_preserve_files(bot_config)
                    self.logger.warning(
                        f"Local changes detected for {bot_name}; force_sync is enabled, forcing repository sync"
                    )
                    if self._force_sync_bot_repo(bot_name, directory, repo_url, preserve_files):
                        return

                    self.logger.warning(f"Auto-update skipped for {bot_name}: force sync failed")
                    return

                self.logger.warning(f"Auto-update skipped for {bot_name}: local changes detected in {directory}")
                return

            remote_result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_COMMAND_TIMEOUT
            )
            if remote_result.returncode != 0:
                self.logger.warning(
                    f"Auto-update skipped for {bot_name}: unable to read origin remote ({remote_result.stderr.strip()})"
                )
                return

            current_remote = remote_result.stdout.strip()
            if current_remote != repo_url:
                self.logger.warning(
                    f"Auto-update skipped for {bot_name}: configured repo URL does not match origin remote"
                )
                return

            pull_result = subprocess.run(
                ['git', 'pull', '--ff-only'],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_COMMAND_TIMEOUT
            )
            if pull_result.returncode == 0:
                self.logger.info(f"Auto-update completed for {bot_name}: {pull_result.stdout.strip()}")
            else:
                self.logger.warning(
                    f"Auto-update failed for {bot_name}: {pull_result.stderr.strip() or pull_result.stdout.strip()}"
                )
        except Exception as e:
            self.logger.warning(f"Auto-update failed for {bot_name}: {e}")

    def start_bot(self, bot_name: str):
        """
        Start a specific bot with corrected directory handling
        """
        if bot_name not in self.config['bots']:
            self.logger.error(f"Bot {bot_name} not found in configuration")
            return False

        bot_config = self.config['bots'][bot_name]
        
        # Use absolute paths
        directory = os.path.join(self.base_dir, bot_config.get('directory', bot_name))
        script = bot_config.get('script', 'main.py')

        self._update_bot_from_repo(bot_name, bot_config, directory)
        
        # Correct path handling: Use absolute paths
        script_path = os.path.join(directory, script)
        color = bot_config.get('color', 'white')

        if not os.path.exists(script_path):
            self.logger.warning(f"Script {script_path} does not exist. Searching for alternatives...")
            try:
                alternative_scripts = [f for f in os.scandir(directory) if f.name.endswith('.py')]
                if alternative_scripts:
                    script_path = os.path.join(directory, alternative_scripts[0].name)
                    self.logger.info(f"Using alternative script: {script_path}")
                else:
                    self.logger.error(f"No Python scripts found in {directory}")
                    return False
            except FileNotFoundError:
                self.logger.error(f"Directory {directory} not found")
                return False

        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            # Print debug information
            self.logger.info(f"Attempting to start {bot_name}")
            self.logger.info(f"Script Path: {script_path}")
            self.logger.info(f"Working Directory: {directory}")

            with self.lock:  # Ensure thread-safe access to processes
                if bot_name in self.processes:
                    self.logger.warning(f"Bot {bot_name} is already running")
                    return False

                process = subprocess.Popen(
                    [sys.executable, script_path],
                    cwd=directory,  # Ensure correct working directory
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=env,
                    universal_newlines=True
                )

                output_thread = threading.Thread(
                    target=self._stream_output, 
                    args=(process, bot_name, color),
                    daemon=True
                )
                output_thread.start()

                self.processes[bot_name] = {
                    'process': process,
                    'thread': output_thread,
                    'script_path': script_path
                }

            self.logger.info(f"Started {bot_name} with PID {process.pid}")
            
            # Save running state to database
            self._save_bot_state(bot_name, True, False)
            
            return True

        except Exception as e:
            self.logger.error(f"Failed to start {bot_name}: {e}")
            return False

    def _process_command_file(self):
        """
        Continuously monitor and process commands from the file.
        """
        while not self.shutdown_event.is_set():
            try:
                if not self._ensure_commands_file_exists(log_if_created=True):
                    time.sleep(5)
                    continue

                # Read commands file
                with open(self.commands_file_path, 'r+') as f:
                    commands = f.readlines()
                    
                    if commands:
                        # Process each command
                        for command in commands:
                            command = command.strip()
                            if not command:
                                continue
                            if command.startswith('#'):
                                continue
                            
                            self.logger.info(f"Processing command: {command}")
                            
                            # Parse command
                            parts = command.split()
                            if len(parts) < 2:
                                self.logger.warning(f"Invalid command format: {command}")
                                continue
                            
                            action, bot_name = parts[0], parts[1]
                            
                            # Execute command
                            try:
                                if action == 'start':
                                    self.start_bot(bot_name)
                                elif action == 'stop':
                                    self.stop_bot(bot_name)
                                elif action == 'restart':
                                    self.restart_bot(bot_name)
                                elif action == 'pause':
                                    self.pause_bot(bot_name)
                                elif action == 'resume':
                                    self.resume_bot(bot_name)
                                elif action == 'status_all':
                                    self.list_bots()
                                else:
                                    self.logger.warning(f"Unknown action: {action}")
                            except Exception as cmd_error:
                                self.logger.error(f"Error executing command {command}: {cmd_error}")
                        
                        # Clear the file after processing
                        f.seek(0)
                        f.truncate()
                
                # Wait before checking again
                time.sleep(COMMAND_CHECK_INTERVAL)

            except FileNotFoundError:
                self._ensure_commands_file_exists(log_if_created=True)
                time.sleep(COMMAND_CHECK_INTERVAL)
            
            except Exception as e:
                self.logger.error(f"Error in command file processing: {e}")
                time.sleep(5)

        self.logger.info("Command file processing thread has stopped.")

    def stop_bot(self, bot_name: str, update_state: bool = True):
        """
        Stop a specific bot with timeout and force kill capabilities.
        If `update_state` is False, the bot's state in the database will not be updated.
        """
        try:
            with self.lock:  # Ensure thread-safe access to processes
                if bot_name not in self.processes:
                    self.logger.warning(f"Bot {bot_name} is not running")
                    return False

                bot_info = self.processes[bot_name]
                process = bot_info['process']

                # Attempt graceful termination
                self.logger.info(f"Attempting to stop {bot_name} (PID {process.pid})...")
                process.terminate()
                try:
                    # Wait for process to exit gracefully
                    process.wait(timeout=PROCESS_FORCE_KILL_TIMEOUT)
                    self.logger.info(f"{bot_name} exited gracefully with code {process.returncode}")
                except subprocess.TimeoutExpired:
                    # Force kill if process doesn't exit
                    self.logger.warning(f"{bot_name} did not exit in time. Forcing termination...")
                    process.kill()
                    process.wait()
                    self.logger.info(f"{bot_name} was forcefully terminated with code {process.returncode}")

                # Clean up
                del self.processes[bot_name]
                self.logger.info(f"Stopped {bot_name}")
                
                # Save stopped state to database if update_state is True
                if update_state:
                    self._save_bot_state(bot_name, False, False)
                
                return True
        except Exception as e:
            self.logger.exception(f"An error occurred while stopping bot {bot_name}: {e}")
            return False

    def restart_bot(self, bot_name: str):
        """
        Restart a specific bot
        """
        with self.lock:  # Ensure thread-safe access to processes
            self.stop_bot(bot_name)
            return self.start_bot(bot_name)

    def pause_bot(self, bot_name: str):
        """
        Pause a specific bot (suspend its process)
        """
        try:
            with self.lock:
                if bot_name not in self.processes:
                    self.logger.warning(f"Bot {bot_name} is not running")
                    return False

                process = self.processes[bot_name]['process']
                process.send_signal(signal.SIGSTOP)
                self.logger.info(f"Paused {bot_name}")
                return True
        except Exception as e:
            self.logger.exception(f"An error occurred while pausing bot {bot_name}: {e}")
            return False

    def resume_bot(self, bot_name: str):
        """
        Resume a specific bot (continue its process)
        """
        try:
            with self.lock:
                if bot_name not in self.processes:
                    self.logger.warning(f"Bot {bot_name} is not running")
                    return False

                process = self.processes[bot_name]['process']
                process.send_signal(signal.SIGCONT)
                self.logger.info(f"Resumed {bot_name}")
                return True
        except Exception as e:
            self.logger.exception(f"An error occurred while resuming bot {bot_name}: {e}")
            return False

    def _stream_output(self, process: subprocess.Popen, bot_name: str, color: str):
        """
        Stream output from a bot process with color coding.
        """
        color_code = self.COLORS.get(color, self.COLORS['white'])
        prefix = f"{color_code}[{bot_name}]{self.COLORS['reset']} "

        def read_stream(stream, is_error=False):
            for line in iter(stream.readline, ''):
                if self.shutdown_event.is_set():
                    break
                if is_error:
                    sys.stderr.write(f"{prefix}{line}")
                    sys.stderr.flush()
                else:
                    sys.stdout.write(f"{prefix}{line}")
                    sys.stdout.flush()

        stdout_thread = threading.Thread(target=read_stream, args=(process.stdout,), daemon=True)
        stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, True), daemon=True)

        stdout_thread.start()
        stderr_thread.start()

        try:
            return_code = process.wait()
            self.logger.info(f"{bot_name} exited with code {return_code}")
        except Exception as e:
            self.logger.error(f"Error while waiting for {bot_name} to exit: {e}")
        finally:
            with self.lock:
                if bot_name in self.processes:
                    del self.processes[bot_name]

        self.logger.info(f"Output streaming for {bot_name} has stopped.")

    def list_bots(self):
        """
        List all configured bots with their current and saved states
        """
        print("\nConfigured Bots:")
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(bot_states)")
                columns = [col[1] for col in cursor.fetchall()]
                
                has_preserved_state = 'preserved_state' in columns
                
                for bot_name, bot_config in self.config['bots'].items():
                    # Prepare query based on schema
                    if has_preserved_state:
                        query = '''
                            SELECT is_running, last_start_time, start_count, preserved_state
                            FROM bot_states 
                            WHERE bot_name = ?
                        '''
                    else:
                        query = '''
                            SELECT is_running, last_start_time, start_count
                            FROM bot_states 
                            WHERE bot_name = ?
                        '''
                    
                    # Get saved state from database
                    cursor.execute(query, (bot_name,))
                    db_state = cursor.fetchone()
                    
                    # Determine current runtime status
                    runtime_status = "Running" if bot_name in self.processes else "Stopped"
                    
                    # Prepare saved state info
                    if db_state:
                        saved_state = "Previously Running" if db_state[0] == 1 else "Previously Stopped"
                        last_start = db_state[1] or "Never"
                        start_count = db_state[2]
                        
                        # Add preserved state info if available
                        if has_preserved_state and len(db_state) > 3:
                            preserved = "Yes" if db_state[3] == 1 else "No"
                            print(f"{bot_name}: {runtime_status} | {saved_state} | Preserved: {preserved}")
                        else:
                            print(f"{bot_name}: {runtime_status} | {saved_state}")
                            
                        print(f"  Script: {bot_config.get('script', 'N/A')}")
                        print(f"  Last Start: {last_start}")
                        print(f"  Total Starts: {start_count}")
                    else:
                        print(f"{bot_name}: {runtime_status}")
                    print("-" * 40)
        except Exception as e:
            self.logger.error(f"Error listing bots: {e}")

    def shutdown(self):
        """
        Stop all bots and exit the program
        """
        self.logger.info("Shutting down all bots...")
        with self.lock:
            for bot_name in list(self.processes.keys()):
                self.stop_bot(bot_name)
        sys.exit(0)

    def get_bot_status(self, bot_name: str):
        """
        Get the status of a specific bot
        """
        try:
            with self.lock:
                if bot_name in self.processes:
                    # Check saved state in database
                    saved_state = "Previously Running" if self._get_bot_saved_state(bot_name) else "Previously Stopped"
                    return f"Bot {bot_name} is running. {saved_state}"
                else:
                    # Check saved state in database
                    saved_state = "Previously Running" if self._get_bot_saved_state(bot_name) else "Previously Stopped"
                    return f"Bot {bot_name} is not running. {saved_state}"
        except Exception as e:
            logging.exception(f"An error occurred while checking status of bot {bot_name}: {e}")
            return "Error retrieving status."

    def process_command(self, command: str) -> str:
        """
        Process a single command string and execute the corresponding action.
        """
        try:
            if command.startswith("status"):
                _, bot_name = command.split()
                return self.get_bot_status(bot_name)
            elif command.startswith("start"):
                _, bot_name = command.split()
                if self.start_bot(bot_name):
                    return f"Bot {bot_name} started successfully."
                else:
                    return f"Failed to start bot {bot_name}."
            elif command.startswith("stop"):
                _, bot_name = command.split()
                if self.stop_bot(bot_name):
                    return f"Bot {bot_name} stopped successfully."
                else:
                    return f"Failed to stop bot {bot_name}."
            elif command.startswith("restart"):
                _, bot_name = command.split()
                if self.restart_bot(bot_name):
                    return f"Bot {bot_name} restarted successfully."
                else:
                    return f"Failed to restart bot {bot_name}."
            else:
                return f"Unknown command: {command}"
        except Exception as e:
            self.logger.exception(f"An error occurred while processing command '{command}': {e}")
            return "Error processing command."

def main():
    parser = argparse.ArgumentParser(description='Advanced Discord Bot Manager')
    parser.add_argument('action', nargs='?', default='start_all', 
                        choices=['start', 'stop', 'restart', 'list', 'start_all', 'shutdown', 'status'], 
                        help='Action to perform (default: start all bots)')
    parser.add_argument('bot', nargs='?', help='Bot name (required for start/stop/restart/status)')
    
    args = parser.parse_args()
    
    bot_manager = BotManager()

    if args.action == 'start':
        if not args.bot:
            print("Please specify a bot to start")
            return
        bot_manager.start_bot(args.bot)
    
    elif args.action == 'stop':
        if not args.bot:
            print("Please specify a bot to stop")
            return
        bot_manager.stop_bot(args.bot)
    
    elif args.action == 'restart':
        if not args.bot:
            print("Please specify a bot to restart")
            return
        bot_manager.restart_bot(args.bot)
    
    elif args.action == 'list':
        bot_manager.list_bots()
    
    elif args.action == 'start_all':
        bot_manager.start_all_bots()
    
    elif args.action == 'shutdown':
        bot_manager.shutdown()

    elif args.action == 'status':
        if not args.bot:
            print("Please specify a bot to check status")
            return
        status = bot_manager.get_bot_status(args.bot)
        print(status)

if __name__ == '__main__':
    main()
