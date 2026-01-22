from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from rpc_client import RpcClient
from datetime import datetime, timezone, timedelta
import requests
import logging
import socket
import json
import base58
import hashlib
from config import config

logging.basicConfig(level=logging.ERROR)


# Custom exception for ElectrumX connection errors
class ElectrumXConnectionError(Exception):
    """Raised when unable to connect to ElectrumX server"""
    pass


# ElectrumX TCP Client Class
class ElectrumXClient:
    def __init__(self, host="localhost", port=50002):
        """
        Initialize ElectrumX TCP client.
        
        Args:
            host: ElectrumX server hostname (default: localhost)
            port: ElectrumX server TCP port (default: 50002 - standard ElectrumX port)
        """
        self.host = host
        self.port = port
        self.socket = None
        self.request_id = 1
        self.protocol_version = None
        self._connected = False

    def _connect(self):
        """Establish TCP connection to ElectrumX server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(30)  # 30 second timeout
            self.socket.connect((self.host, self.port))
            self._connected = True
            
            # Perform protocol handshake
            self._handshake()
        except (socket.error, ConnectionRefusedError, OSError) as e:
            self._connected = False
            raise ElectrumXConnectionError(
                f"Divi ElectrumX server is not running. "
                f"Please ensure ElectrumX is running on {self.host}:{self.port}"
            )

    def _handshake(self):
        """Perform protocol handshake with server.version"""
        try:
            response = self._call("server.version", ["python-divi-rpc", "1.4"])
            if isinstance(response, list) and len(response) >= 2:
                self.protocol_version = response[1]
        except Exception as e:
            logging.warning(f"Handshake warning: {e}")

    def _call(self, method, params=None):
        """Make JSON-RPC call to ElectrumX server"""
        if not self._connected or self.socket is None:
            self._connect()
        
        params = params or []
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self.request_id
        }
        self.request_id += 1
        
        try:
            # Send request with newline termination
            request_str = json.dumps(request) + "\n"
            self.socket.sendall(request_str.encode('utf-8'))
            
            # Read response line by line (newline-delimited JSON)
            # ElectrumX sends one JSON object per line
            response_data = b""
            while True:
                chunk = self.socket.recv(4096)  # Read in chunks
                if not chunk:
                    break
                response_data += chunk
                if b"\n" in response_data:  # Found newline, complete response
                    # Extract only up to the first newline
                    response_data = response_data.split(b"\n", 1)[0]
                    break
            
            if not response_data:
                raise Exception("Empty response from ElectrumX server")
            
            response_str = response_data.decode('utf-8').strip()
            if not response_str:
                raise Exception("Empty response string from ElectrumX server")
            
            response = json.loads(response_str)
            
            if "error" in response and response["error"] is not None:
                error_msg = response["error"].get("message", str(response["error"]))
                raise Exception(f"ElectrumX error: {error_msg}")
            
            return response.get("result")
        except socket.timeout:
            self._connected = False
            raise ElectrumXConnectionError(
                f"Divi ElectrumX server request timeout. "
                f"Please ensure ElectrumX is running on {self.host}:{self.port}"
            )
        except (socket.error, ConnectionRefusedError, OSError) as e:
            self._connected = False
            raise ElectrumXConnectionError(
                f"Divi ElectrumX server is not running. "
                f"Please ensure ElectrumX is running on {self.host}:{self.port}"
            )
        except json.JSONDecodeError as e:
            raise Exception(f"ElectrumX response parse error: {e}")
        except Exception as e:
            self._connected = False
            raise Exception(f"ElectrumX error: {e}")

    def get_balance(self, scripthash):
        """Get balance for a script hash"""
        return self._call("blockchain.scripthash.get_balance", [scripthash])

    def get_history(self, scripthash):
        """Get transaction history for a script hash"""
        return self._call("blockchain.scripthash.get_history", [scripthash])

    def get_transaction(self, tx_hash):
        """Get raw transaction hex by transaction hash"""
        return self._call("blockchain.transaction.get", [tx_hash])

    def broadcast_transaction(self, raw_tx):
        """Broadcast raw transaction to network"""
        return self._call("blockchain.transaction.broadcast", [raw_tx])

    def list_unspent(self, scripthash):
        """Get unspent UTXOs for a script hash"""
        return self._call("blockchain.scripthash.listunspent", [scripthash])

    def estimate_fee(self, blocks=2):
        """Estimate fee for transaction confirmation"""
        result = self._call("blockchain.estimatefee", [blocks])
        # DIVI uses fixed fee of 0.0001, return as float
        return result if result != -1 else 0.0001

    def relay_fee(self):
        """Get minimum relay fee"""
        result = self._call("blockchain.relayfee", [])
        # DIVI uses fixed fee of 0.0001, return as float
        return result if result else 0.0001

    def close(self):
        """Close the connection"""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
            self._connected = False


# Address/Vault Owner Key to Script Hash Conversion Helper
def divi_address_to_scripthash(address: str) -> str:
    """
    Convert DIVI address or vault_owner_key to ElectrumX script hash.
    
    Both addresses and vault_owner_keys use the same base58 encoding format,
    so this function handles both types.
    
    Process:
    1. Decode DIVI address/vault_owner_key using base58 (skip first byte, extract next 20 bytes = hash160)
    2. Create P2PKH scriptPubKey: 76a914<hash160>88ac
    3. SHA256 hash the scriptPubKey
    4. Reverse the hash bytes (little-endian for ElectrumX)
    5. Return as hex string
    """
    try:
        # Decode base58 address
        decoded = base58.b58decode(address)
        
        # Skip first byte (version), extract next 20 bytes (hash160)
        if len(decoded) < 21:
            raise ValueError("Invalid address length")
        
        hash160 = decoded[1:21]  # Extract 20 bytes after version byte
        
        # Create P2PKH scriptPubKey: OP_DUP OP_HASH160 <hash160> OP_EQUALVERIFY OP_CHECKSIG
        # 76 = OP_DUP, a9 = OP_HASH160, 14 = push 20 bytes, 88 = OP_EQUALVERIFY, ac = OP_CHECKSIG
        script_pubkey = bytes([0x76, 0xa9, 0x14]) + hash160 + bytes([0x88, 0xac])
        
        # SHA256 hash the scriptPubKey
        sha256_hash = hashlib.sha256(script_pubkey).digest()
        
        # Reverse the hash bytes (little-endian for ElectrumX)
        reversed_hash = sha256_hash[::-1]
        
        # Return as hex string
        return reversed_hash.hex()
    except Exception as e:
        raise ValueError(f"Failed to convert address to scripthash: {e}")


app = FastAPI(
    title="Divi Blockchain API",
    description="API for interacting with the Divi Blockchain via RPC calls",
    version="1.1.0"
)

# Cache settings
cache = {"data": None, "timestamp": None}
CACHE_DURATION = timedelta(hours=5)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    # Log the error for debugging
    logging.error(f"HTTP Exception: {exc.detail}")

    # Check if detail is a string and jsonify it
    content = (
        {"error": exc.status_code, "message": exc.detail}
        if isinstance(exc.detail, str)
        else exc.detail
    )
    return JSONResponse(status_code=exc.status_code, content=content)

@app.exception_handler(Exception)
async def generic_500_handler(request: Request, exc: Exception) :
    # Log the error for debugging
    logging.error(f"Internal server error: {exc}")

    # Return a funny custom message for the user
    return JSONResponse(
        status_code=500,
        content={
            "error": 500,
            "message": "Oops! Looks like something went wrong. Either the universe just exploded, or you used the wrong API function. Try again, newb!"
        },
    )

# CORS middleware for handling cross-origin requests during testing on local machine
origins = [
    "https://api.yourdomain.com",  # Only the primary domain
    # "http://localhost",           # Uncomment for local development
    # "http://localhost:3000",      # Uncomment for local frontend testing
    # "https://YOUR_IP_ADDRESS",    # Only if necessary for direct IP access
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # Restrict to specific origins
    allow_credentials=False,          # Set to False if not using credentials like cookies
    allow_methods=["GET", "POST"],    # Restrict to necessary methods
    allow_headers=["Content-Type", "Authorization"],  # Specify only required headers
)
rpc = RpcClient()
# Initialize ElectrumX client with configurable host/port
# Defaults: localhost:50002 (can be overridden via ELECTRUMX_HOST and ELECTRUMX_PORT env vars)
dex_client = ElectrumXClient(host=config['electrumx_host'], port=config['electrumx_port'])

# Middleware for logging IP addresses
@app.middleware("http")
async def log_requests(request: Request, call_next):
    ip = request.client.host
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"IP Address: {ip}, Time: {current_time}")
    response = await call_next(request)
    return response


# RPC Response hander
def handle_rpc_response(result):
    # Check if the result itself is a dictionary with a "result" key
    if isinstance(result, dict) and "result" in result:
        # Unwrap the inner result if it has "result" key at the top level
        result = result["result"]

    # Return structured response
    return {
        "result": result,
        "error": None,
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }

# RPC Error handler
def handle_rpc_error(error_msg):
    return {
        "result": None,
        "error": {
            "message": error_msg
        },
        "timestamp": datetime.now(timezone.utc).isoformat()  # Add UTC timestamp
    }

def rpc_call_wrapper(callable, *args):
    try:
        result = callable(*args)
        return handle_rpc_response(result)
    except requests.exceptions.ConnectionError as e:
        logging.error(f"ConnectionError occurred: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable. Try again later.")
    except requests.exceptions.Timeout as e:
        logging.error(f"Timeout occurred: {e}")
        raise HTTPException(
            status_code=504,
            detail="Request Timeout. Service took too long to respond. Try again later."
        )
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTPError occurred: {e}")
        raise HTTPException(
            status_code=401,
            detail=f"Oops! There was an HTTP error: {str(e)}. Check your request and try again."
        )
    except Exception as e:
        # Log the actual exception to help with debugging
        logging.error(f"General Exception occurred: {e}")
        raise HTTPException(
            status_code=500,
            detail="Oops! Looks like something broke. Either the universe just exploded, or you used the wrong API function. Try again, newb!"
        )

# Convert string "true" or "false" to bool manually
def str_to_bool(value: str) -> bool:
    return value.lower() == 'true'


# Convert string "true" or "false" to int
def str_to_int_bool(value: str) -> int:
    return 1 if str_to_bool(value) else 0

# Ping server
@app.get("/ping", summary="Ping the server", description="Returns a 'pong' message to check server connectivity.")
async def ping():
    return rpc.ping()


# Current block count
@app.get("/blockcount", summary="Get Block Count",
         description="Fetches the current block count of the Divi blockchain.")
async def get_block_count():
    return rpc_call_wrapper(rpc.get_block_count)

# Information about a specific block's hash by block number
@app.get("/blockhash/{block}", summary="Get Block Hash",
         description="Fetches the block hash for a specific block number.")
async def get_block_hash(block: str):
    # Validate the block number format to ensure it's a non-negative integer
    if not block.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Invalid block number format. Block number should be a non-negative integer."
        )

    # Convert the validated block number to integer
    block_num = int(block)

    # Proceed with the RPC call
    try:
        return rpc_call_wrapper(rpc.get_block_hash, block_num)
    except Exception as e:
        logging.error(f"Error while fetching block hash: {e}")
        raise HTTPException(
            status_code=404,
            detail="Block not found. The provided block number does not exist."
        )

# Information about a specific block
@app.get("/block/{hash}", summary="Get Block by Hash",
         description="Fetches the block information for a given block hash.")
async def get_block(hash: str):
    # Validate the hash format
    if not is_valid_hex_hash(hash, 64):
        raise HTTPException(
            status_code=400,
            detail="Invalid block hash format. Expected a 64-character hexadecimal string."
        )

    # If the hash is valid, proceed with the RPC call
    try:
        return rpc_call_wrapper(rpc.get_block, hash)
    except Exception as e:
        logging.error(f"Error while fetching block: {e}")
        # Customize error message for non-existent block
        raise HTTPException(
            status_code=404,
            detail="Block not found. The provided block hash does not exist."
        )

# Current General Blockchain Stats
@app.get("/info")
async def get_info() :
    return rpc_call_wrapper(rpc.get_info)

# Total number of connected peers
@app.get("/connectioncount", summary="Get Total Number of Connected Peers",
         description="Returns the current number of peers connected to the node. This includes both incoming and outgoing connections, providing an overview of the network's health.")
async def get_connection_count():
    return rpc_call_wrapper(rpc.get_connection_count)

# Filtered peers list
def split_ip_port(address):
    # For IPv6 with brackets, remove them and split on `]:`
    if address.startswith('['):
        ip = address[1:].split(']:')[0]
        port = address.split(']:')[-1]
    else:
        # For IPv4, just split on `:`
        ip, port = address.split(':')
    return ip, port

@app.get("/getpeers", summary="Get Filtered Peer List",
         description="Returns a list of peers filtered by DIVI Core version and block height.")
async def get_peers(include_ipv6: bool = False):
    global cache

    # Check cache
    now = datetime.now(timezone.utc)
    if cache["data"] and cache["timestamp"] and now - cache["timestamp"] < CACHE_DURATION:
        return cache["data"]

    try:
        # Get current block count
        block_count = rpc.get_block_count()
        if block_count is None:
            raise HTTPException(status_code=500, detail="Unable to retrieve block count.")

        # Get peer information
        peer_info = rpc.get_peer_info()
        if not peer_info:
            raise HTTPException(status_code=500, detail="Unable to retrieve peer information.")

        # Filter peers based on criteria
        filtered_peers = {}
        for peer in peer_info:
            subver = peer.get("subver", "")
            starting_height = peer.get("startingheight", 0)
            addr = peer.get("addr", "")

            # Exclude IPv6 addresses if include_ipv6 is False
            if not include_ipv6 and addr.startswith('['):
                continue

            # Extract the IP and port from the address
            ip_address, port = split_ip_port(addr)

            # Check subversion and block height criteria
            if subver >= "DIVI Core: 3.0.0.0" and starting_height >= block_count - 1000:
                if subver not in filtered_peers:
                    filtered_peers[subver] = []
                filtered_peers[subver].append({"ip": ip_address, "port": port})

        # Structure the result
        result = {
            "result": [{"core": ver, "peers": peers} for ver, peers in filtered_peers.items()],
            "error": None,
            "id": 1,
            "timestamp_utc": now.isoformat()
        }

        # Update cache
        cache["data"] = result
        cache["timestamp"] = now

        return result

    except Exception as e:
        return {"error": str(e), "timestamp": now.isoformat()}


# Check transaction details
@app.get("/tx/{txid}", summary="Get Transaction",
         description="Fetches details about a specific transaction based on its txid.")
async def get_transaction(txid: str):
    return rpc_call_wrapper(rpc.get_raw_transaction, txid, True)


# Get address or vault owner key balance current and total received
@app.get("/getaddressbalance/{address}/{isVault}",
         summary="Get Address Balance",
         description="Fetches the current balance and total received amount for a specified address or vault owner key. Use the 'isVault' boolean to lookup a vault owner key.")
async def get_address_balance(address: str, isVault: bool = False):

    return rpc_call_wrapper(rpc.get_address_balance, address, isVault)

# Get address or vault owner key deltas (transaction history)
@app.get("/getaddressdeltas/{address}/{isVault}",
         summary = "Get Address Transaction History (Deltas)",
         description = "Returns the list of transaction deltas (history of transactions) for a specified address or vault owner key. This will include both spent and unspent transaction history. Use the 'isVault' boolean to lookup a vault owner key.")
async def get_address_deltas(address: str, isVault: bool = False):

    return rpc_call_wrapper(rpc.get_address_deltas, address, isVault)

# Get address transaction IDs (unspent transactions)
@app.get("/getaddresstxids/{address}/{isVault}",
         summary="Get Address or Vault Owner Key Transaction IDs",
         description="Fetches the list of transaction IDs associated with the specified address or vault owner key. This can include all transaction IDs, use the 'isVault' boolean to lookup a vault owner key.")
async def get_address_txids(address: str, isVault: bool = False):

    return rpc_call_wrapper(rpc.get_address_txids, address, isVault)

# Get address UTXOs for an address or vault owner key
@app.get("/getaddressutxos/{address}/{isVault}",
         summary = "Get Address or Vault Owner Key UTXOs",
         description = "Fetches the list of Unspent Transaction Outputs (UTXOs) associated with the specified address or vault owner key. Use the 'isVault' boolean to lookup a vault owner key.")
async def get_address_utxos(address: str, isVault: bool = False):

    return rpc_call_wrapper(rpc.get_address_utxos, address, isVault)


# Decode raw transaction
@app.get("/decode-raw-tx/{hex}",
         summary="Decode Raw Transaction",
         description="Decodes a raw transaction hex string and returns detailed information about the transaction, including inputs, outputs, and other metadata.")
async def decode_raw_transaction(hex: str):
    return rpc_call_wrapper(rpc.decode_raw_transaction, hex)


# Send raw transaction
class SendRawTransactionRequest(BaseModel):
    hexstring: str

@app.post("/sendrawtransaction/{hexstring}",
          summary="Send Raw Transaction",
          description="Broadcasts a raw transaction to the blockchain network.")

async def send_raw_transaction(hexstring: str):
    # Validate that hexstring is a non-empty string
    if not hexstring:
        raise HTTPException(status_code=400, detail="Invalid hexstring provided")

    # Call the RPC client with the hexstring
    return rpc_call_wrapper(rpc.send_raw_transaction, hexstring)



# Get current mempool transactions
@app.get("/getrawmempool",
         summary = "Get Current Mempool Transactions",
         description = "Fetches the list of transaction IDs currently in the node's memory pool (mempool). These are unconfirmed transactions that are awaiting inclusion in the next block.")
async def get_raw_mempool() :
    return rpc_call_wrapper(rpc.get_raw_mempool)


# Get mempool info
@app.get("/getmempoolinfo",
         summary="Get Mempool Info",
         description="Returns detailed information about the current state of the memory pool (mempool). This includes size, memory usage, and other statistics regarding pending transactions.")
async def get_mempool_info():
    return rpc_call_wrapper(rpc.get_mempool_info)


# Get lottery winners (if no block height is provided, fetch the latest)
@app.get(
    "/getlottery",
    summary = "Get Current Lottery Winners",
    description = (
            "Fetches the list of lottery candidates for a specific block if a block height is provided. "
            "If no block height is entered, it returns the current list of candidates. "
            "On the block where the lottery payout occurs, the list is purged."
    )
)

async def get_lottery(blockheight: Optional[int] = None) :
    try :
        if blockheight is not None :
            # Blockheight provided, fetch for the specific block
            result = rpc.get_lottery_block_winners(blockheight)
        else :
            # No blockheight provided, fetch latest lottery winners
            result = rpc.get_lottery_block_winners()
        return handle_rpc_response(result)
    except Exception as e :
        return handle_rpc_error(str(e))


# Helper functions for validation and error handling
def is_valid_hex_hash(hash_str: str, length: int = 64) -> bool:
    """Validate if string is a valid hexadecimal hash of specified length."""
    return len(hash_str) == length and all(c in '0123456789abcdefABCDEF' for c in hash_str)


def get_scripthash_from_identifier(identifier: str) -> str:
    """
    Convert identifier (address, vault_owner_key, or script hash) to script hash.
    
    - Script hash (64 hex chars): Returns as-is (lowercased)
    - DIVI address or vault_owner_key: Converts to script hash using base58 decoding
    """
    # Check if it's a script hash (64 hex characters)
    if is_valid_hex_hash(identifier, 64):
        return identifier.lower()
    else:
        # Assume it's a DIVI address or vault_owner_key (both use same base58 encoding)
        # Convert to script hash
        return divi_address_to_scripthash(identifier)


# ElectrumX (DEX) Endpoints
@app.get("/dex/balance/{identifier}",
         summary="Get Balance with Vault Breakdown",
         description="Get balance with vault breakdown for address, vault_owner_key, or script hash.")
async def dex_get_balance(identifier: str):
    try:
        scripthash = get_scripthash_from_identifier(identifier)
        result = dex_client.get_balance(scripthash)
        
        # Convert numeric values to strings as per ElectrumX format
        if isinstance(result, dict):
            # Ensure confirmed and unconfirmed are strings
            if "confirmed" in result:
                result["confirmed"] = str(result["confirmed"])
            if "unconfirmed" in result:
                result["unconfirmed"] = str(result["unconfirmed"])
            # Handle breakdown if present
            if "breakdown" in result and isinstance(result["breakdown"], dict):
                if "vault_balance" in result["breakdown"]:
                    result["breakdown"]["vault_balance"] = str(result["breakdown"]["vault_balance"])
                if "spendable_balance" in result["breakdown"]:
                    result["breakdown"]["spendable_balance"] = str(result["breakdown"]["spendable_balance"])
        
        return handle_rpc_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ElectrumXConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logging.error(f"Error fetching balance: {e}")
        raise HTTPException(status_code=503, detail=f"ElectrumX service error: {str(e)}")


@app.get("/dex/history/{identifier}",
         summary="Get Transaction History",
         description="Get transaction history for address, vault_owner_key, or script hash.")
async def dex_get_history(identifier: str):
    try:
        scripthash = get_scripthash_from_identifier(identifier)
        result = dex_client.get_history(scripthash)
        return handle_rpc_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ElectrumXConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logging.error(f"Error fetching history: {e}")
        raise HTTPException(status_code=503, detail=f"ElectrumX service error: {str(e)}")


@app.get("/dex/transaction/{tx_hash}",
         summary="Get Raw Transaction",
         description="Get raw transaction hex by transaction hash")
async def dex_get_transaction(tx_hash: str):
    # Validate tx_hash format (64 hex chars)
    if not is_valid_hex_hash(tx_hash, 64):
        raise HTTPException(
            status_code=400,
            detail="Invalid transaction hash format. Expected a 64-character hexadecimal string."
        )
    
    try:
        result = dex_client.get_transaction(tx_hash)
        return handle_rpc_response(result)
    except ElectrumXConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logging.error(f"Error fetching transaction: {e}")
        raise HTTPException(status_code=503, detail=f"ElectrumX service error: {str(e)}")


@app.post("/dex/broadcast/{raw_tx}",
          summary="Broadcast Raw Transaction",
          description="Broadcast raw transaction to network")
async def dex_broadcast_transaction(raw_tx: str):
    # Validate raw_tx is non-empty hex string
    if not raw_tx:
        raise HTTPException(status_code=400, detail="Invalid raw transaction hex provided")
    
    if not all(c in '0123456789abcdefABCDEF' for c in raw_tx):
        raise HTTPException(status_code=400, detail="Raw transaction must be a valid hexadecimal string")
    
    try:
        result = dex_client.broadcast_transaction(raw_tx)
        return handle_rpc_response(result)
    except ElectrumXConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logging.error(f"Error broadcasting transaction: {e}")
        raise HTTPException(status_code=503, detail=f"ElectrumX service error: {str(e)}")


@app.get("/dex/unspent/{identifier}",
         summary="Get Unspent UTXOs",
         description="Get unspent UTXOs for address, vault_owner_key, or script hash.")
async def dex_get_unspent(identifier: str):
    try:
        scripthash = get_scripthash_from_identifier(identifier)
        result = dex_client.list_unspent(scripthash)
        
        # Convert value to string for consistency
        if isinstance(result, list):
            for utxo in result:
                if isinstance(utxo, dict) and "value" in utxo:
                    utxo["value"] = str(utxo["value"])
        
        return handle_rpc_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ElectrumXConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logging.error(f"Error fetching unspent: {e}")
        raise HTTPException(status_code=503, detail=f"ElectrumX service error: {str(e)}")


@app.get("/dex/fee/estimate",
         summary="Get Fee Estimate",
         description="Get fee estimate (DIVI uses fixed 0.0001 DIVI fee)")
async def dex_get_fee_estimate(blocks: int = 2):
    try:
        result = dex_client.estimate_fee(blocks)
        return handle_rpc_response(result)
    except ElectrumXConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logging.error(f"Error fetching fee estimate: {e}")
        raise HTTPException(status_code=503, detail=f"ElectrumX service error: {str(e)}")


@app.get("/dex/fee/relay",
         summary="Get Minimum Relay Fee",
         description="Get minimum relay fee (DIVI uses fixed 0.0001 DIVI fee)")
async def dex_get_relay_fee():
    try:
        result = dex_client.relay_fee()
        return handle_rpc_response(result)
    except ElectrumXConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logging.error(f"Error fetching relay fee: {e}")
        raise HTTPException(status_code=503, detail=f"ElectrumX service error: {str(e)}")


# Run app if executed directly
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config['host'], port=config['port'])