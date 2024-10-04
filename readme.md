# Divi Blockchain RPC API

This repository provides a FastAPI-based application to interact with the Divi Blockchain using its RPC interface. The API allows you to perform various blockchain operations, such as retrieving block information, sending transactions, and more, all through HTTP endpoints.

## Features

- Fetch blockchain information such as block count, block data, and transaction details.
- Retrieve UTXOs, transaction history, and balances for addresses.
- Send raw transactions to the network.
- Mempool information and lottery block winners information.
- Cross-origin support (CORS) for local development.

## Prerequisites

- Python 3.8 or later
- A running Divi blockchain node with RPC enabled
- RPC credentials configured either in a configuration file (`divi.conf`) or as environment variables.

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/7h3v01c3/python-divi-rpc.git
   cd python-divi-rpc
   ```

2. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure your Divi node's RPC credentials:

   Ensure you have a `divi.conf` file with the proper `rpcuser`, `rpcpassword`, and `rpcport` configured. The config file is typically located in:
   
   - **Windows**: `C:\Users\YourUser\AppData\Roaming\DIVI\divi.conf`
   - **macOS**: `~/Library/Application Support/DIVI/divi.conf`
   - **Linux**: `~/.divi/divi.conf`
   
   Alternatively, set environment variables for `RPC_USER`, `RPC_PASS`, and `RPC_PORT`:
   
   ```bash
   export RPC_USER=your_rpc_user
   export RPC_PASS=your_rpc_password
   export RPC_PORT=your_rpc_port  # default is 51473
   ```

## Running the API

1. Start the FastAPI server using `uvicorn`:

   ```bash
   uvicorn main:app --reload
   ```

   The server will run on `http://127.0.0.1:8000/`.

2. Visit the automatically generated API docs at `http://127.0.0.1:8000/docs` to interact with the API.

## Example Usage

Below are some example API calls that can be made using `curl` or any HTTP client:

- **Ping the server:**

   ```bash
   curl http://127.0.0.1:8000/ping
   ```

- **Get the current block count:**

   ```bash
   curl http://127.0.0.1:8000/blockcount
   ```

- **Get block information by hash:**

   ```bash
   curl http://127.0.0.1:8000/block/{block_hash}
   ```

- **Send a raw transaction:**

   ```bash
   curl -X POST "http://127.0.0.1:8000/sendrawtransaction" \
        -H "Content-Type: application/json" \
        -d '{"hexstring": "your_raw_transaction_hex"}'
   ```

## API Endpoints

The following is a summary of the available API endpoints:

- `GET /ping`: Ping the server to ensure it's running.
- `GET /blockcount`: Get the current block count of the Divi blockchain.
- `GET /block/{hash}`: Fetch block information by its hash.
- `GET /tx/{txid}`: Get transaction details by transaction ID.
- `GET /getaddressbalance/{address}/{isVault}`: Get the balance for a given address.
- `POST /sendrawtransaction`: Broadcast a raw transaction to the blockchain.

For a complete list of endpoints, visit the API documentation at `http://127.0.0.1:8000/docs`.

## Configuration

The RPC credentials are read from either the `divi.conf` file or environment variables. The following environment variables can be used:

- `RPC_USER`: Your Divi node's RPC username.
- `RPC_PASS`: Your Divi node's RPC password.
- `RPC_PORT`: The RPC port your Divi node is using (default: 51473).

## Logging

Yes, logging in Python can easily be made optional by allowing users to configure it. You can provide a mechanism to either disable logging completely or set a desired logging level (such as only logging errors). This can be done by making the logging setup in the `main.py` or `rpc_client.py` file configurable, and adding instructions in the `README.md` for how to do so.

### Update to the Code

You can modify the `main.py` and `rpc_client.py` to allow for optional logging using environment variables or config parameters. Here's a way to make it configurable:

#### Modify `main.py`:

```python
import os
import logging

# Set logging level based on environment variable (default to INFO)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging with the set log level
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))

# Example API definition continues...
```

#### Modify `rpc_client.py`:

Since `main.py` configures the logging globally, no changes are needed in `rpc_client.py`. But if you want fine-grained control over logging, you can wrap logging calls with a condition:

```python
import logging

# Check if logging is enabled globally (this can also be configured using an environment variable)
if logging.getLogger().isEnabledFor(logging.DEBUG):
    logging.debug(f"Debug log message here")
```


## Logging

By default, the API logs all RPC requests and responses for debugging and monitoring purposes. You can control the logging level or disable logging entirely using an environment variable.

### Disabling Logging

To disable logging, set the environment variable `LOG_LEVEL` to `ERROR`, which will only log critical errors and suppress other information or debug logs.

1. **Linux/macOS** (using `bash`):
   ```bash
   export LOG_LEVEL=ERROR
   ```

2. **Windows** (using `cmd`):
   ```cmd
   set LOG_LEVEL=ERROR
   ```

Alternatively, to **disable logging completely**, set the `LOG_LEVEL` to `CRITICAL`:
```bash
export LOG_LEVEL=CRITICAL
```

### Custom Logging Levels

The following logging levels are available, listed in increasing order of severity:
- `DEBUG`: Logs all debugging information, useful for troubleshooting.
- `INFO`: Logs general information (default).
- `WARNING`: Logs warning messages.
- `ERROR`: Logs only error messages.
- `CRITICAL`: Logs only critical errors (most severe).

To set a custom logging level, use:

```bash
export LOG_LEVEL=DEBUG  # or INFO, WARNING, ERROR, CRITICAL
```



## CORS PLEASE READ!! (Cross-Origin Resource Sharing)

**CORS** is enabled by default in this application to allow cross-origin requests, which is helpful during development. However, enabling CORS for all origins can expose your API to security vulnerabilities, especially in production environments.

### Disabling or Restricting CORS

1. **Disabling CORS** (Recommended for production):

   To disable CORS entirely (no external domains allowed to make requests), comment out or remove the following block in `main.py`:

   ```python
   # app.add_middleware(
   #     CORSMiddleware,
   #     allow_origins=["*"],
   #     allow_credentials=True,
   #     allow_methods=["*"],
   #     allow_headers=["*"],
   # )
   ```

2. **Restricting CORS to Trusted Domains**:

   If you need to allow only specific trusted domains to make requests, modify the `allow_origins` list:

   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://trusted-domain.com"],  # Replace with your domain
       allow_credentials=True,
       allow_methods=["GET", "POST"],  # Limit allowed methods for more security
       allow_headers=["Content-Type"],  # Limit allowed headers
   )
   ```

3. **Enabling CORS for Development**:

   During development, you can leave CORS enabled for all origins:

   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["*"],  # Allows all domains (only for development)
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

### Caution

- Allowing `allow_origins=["*"]` in production can expose your API to security risks. Ensure you review and restrict CORS as needed based on your use case.

---

## License

This project is licensed under the MIT License.
