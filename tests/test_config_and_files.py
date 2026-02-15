import os
import yaml

def test_bot_config_exists():
    path = os.path.join(os.path.dirname(__file__), '..', 'bot_config.yaml')
    path = os.path.abspath(path)
    assert os.path.exists(path), "bot_config.yaml must exist"
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    assert 'bots' in data, "bot_config.yaml should contain 'bots' mapping"

def test_commands_example_exists():
    path = os.path.join(os.path.dirname(__file__), '..', 'bot_commands.txt')
    path = os.path.abspath(path)
    assert os.path.exists(path), "bot_commands.txt should exist"
