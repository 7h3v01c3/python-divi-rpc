import os
import sys

def get_conf_path():
    """
    Determine the appropriate configuration file path based on the platform and read the rpcuser, rpcpassword, and rpcport.
    """
    if sys.platform.startswith('win'):
        path = os.path.join(os.getenv('APPDATA'), 'DIVI', 'divi.conf')
    elif sys.platform == 'darwin':
        path = os.path.join(os.path.expanduser("~"), 'Library', 'Application Support', 'DIVI', 'divi.conf')
    elif sys.platform.startswith('linux'):
        path = os.path.join(os.path.expanduser("~"), '.divi', 'divi.conf')
    else:
        raise OSError(f"Unsupported platform: {sys.platform}")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Configuration file not found: {path}")

    config = {
        'rpc_user': None,
        'rpc_password': None,
        'rpc_port': None
    }

    # Read the configuration file
    with open(path, 'r') as f:
        for line in f:
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()

            if key == "rpcuser":
                config['rpc_user'] = value
            elif key == "rpcpassword":
                config['rpc_password'] = value
            elif key == "rpcport":
                config['rpc_port'] = int(value)

    # Fallback to environment variables
    config['rpc_user'] = config['rpc_user'] or os.getenv('RPC_USER')
    config['rpc_password'] = config['rpc_password'] or os.getenv('RPC_PASS')
    config['rpc_port'] = config['rpc_port'] or int(os.getenv('RPC_PORT', 51473))  # Default to port 51473

    if not config['rpc_user'] or not config['rpc_password']:
        raise ValueError("Missing rpcuser or rpcpassword in configuration file or environment variables.")

    return config

# Load RPC credentials
config = get_conf_path()
RPC_URL = f"http://{config['rpc_user']}:{config['rpc_password']}@localhost:{config['rpc_port']}"
