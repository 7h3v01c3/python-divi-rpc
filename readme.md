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

All RPC requests and responses are logged for debugging purposes. Logs include the RPC method, parameters, and responses from the blockchain node.

## License

This project is licensed under the MIT License.