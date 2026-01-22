import os
import sys
from dotenv import load_dotenv
from typing import Optional, Dict, Tuple

# Load environment variables from .env files
load_dotenv()
load_dotenv('.env.local')
load_dotenv('.env.development.local')
load_dotenv('.env.production.local')

# Constants (Replace Magic Numbers/Strings)
DEFAULT_RPC_PORT = 51473
DEFAULT_RPC_HOST = '127.0.0.1'
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8000
# ElectrumX (DEX) server defaults
DEFAULT_ELECTRUMX_HOST = 'localhost'
DEFAULT_ELECTRUMX_PORT = 50002  # Standard ElectrumX TCP port
CONFIG_FILE_NAME = 'divi.conf'


def get_platform_config_path() -> str:
    """Get platform-specific config file path."""
    if sys.platform.startswith('win'):
        return os.path.join(
            os.getenv('APPDATA'), 'DIVI', CONFIG_FILE_NAME
        )
    elif sys.platform == 'darwin':
        return os.path.join(
            os.path.expanduser("~"),
            'Library', 'Application Support', 'DIVI', CONFIG_FILE_NAME
        )
    elif sys.platform.startswith('linux'):
        return os.path.join(
            os.path.expanduser("~"), '.divi', CONFIG_FILE_NAME
        )
    else:
        raise OSError(f"Unsupported platform: {sys.platform}")


def parse_config_line(line: str) -> Optional[Tuple[str, str]]:
    """Parse a single config file line into key-value pair."""
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    return (key.strip(), value.strip())


def load_config_from_file(path: str) -> Dict[str, str]:
    """Load configuration from divi.conf file."""
    config = {}
    if not os.path.exists(path):
        return config

    with open(path, 'r') as f:
        for line in f:
            parsed = parse_config_line(line)
            if parsed:
                key, value = parsed
                config[key] = value

    return config


def get_env_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable value."""
    return os.getenv(key, default)


def get_env_int(key: str, default: int) -> int:
    """Get environment variable as integer."""
    value = os.getenv(key)
    return int(value) if value else default


def apply_file_config(config: Dict, file_config: Dict[str, str]) -> None:
    """Apply file configuration values to config dict."""
    if "rpcuser" in file_config:
        config['rpc_user'] = file_config["rpcuser"]
    if "rpcpassword" in file_config:
        config['rpc_password'] = file_config["rpcpassword"]
    if "rpcport" in file_config:
        config['rpc_port'] = int(file_config["rpcport"])
    if "rpcbind" in file_config:
        config['rpc_host'] = file_config["rpcbind"]


def validate_config(config: dict) -> None:
    """Validate required configuration values."""
    if not config.get('rpc_user') or not config.get('rpc_password'):
        raise ValueError(
            "Missing rpcuser or rpcpassword in configuration file "
            "or RPC_USER or RPC_PASS environment variables."
        )


def get_conf_path() -> Dict:
    """
    Load configuration from environment variables and divi.conf file.

    Priority: File config > Environment variables > Defaults
    """
    # Initialize with environment variables and defaults
    config = {
        'rpc_user': get_env_value('RPC_USER'),
        'rpc_password': get_env_value('RPC_PASS'),
        'rpc_port': get_env_int('RPC_PORT', DEFAULT_RPC_PORT),
        'rpc_host': get_env_value('RPC_HOST', DEFAULT_RPC_HOST),
        'host': get_env_value('HOST', DEFAULT_HOST),
        'port': get_env_int('PORT', DEFAULT_PORT),
        # ElectrumX (DEX) server configuration
        'electrumx_host': get_env_value('ELECTRUMX_HOST', DEFAULT_ELECTRUMX_HOST),
        'electrumx_port': get_env_int('ELECTRUMX_PORT', DEFAULT_ELECTRUMX_PORT)
    }

    # Override with file configuration if enabled
    if get_env_value('IGNORE_DIVID_CONF', 'FALSE') == 'FALSE':
        config_path = get_platform_config_path()
        file_config = load_config_from_file(config_path)
        apply_file_config(config, file_config)

    validate_config(config)
    return config


# Load RPC credentials
config = get_conf_path()
RPC_URL = (
    f"http://{config['rpc_user']}:{config['rpc_password']}"
    f"@{config['rpc_host']}:{config['rpc_port']}"
)
