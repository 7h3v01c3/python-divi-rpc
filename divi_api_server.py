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
from config import  config

logging.basicConfig(level=logging.ERROR)

app = FastAPI(
    title="Divi Blockchain API",
    description="API for interacting with the Divi Blockchain via RPC calls",
    version="1.0.0"
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
async def generic_500_handler(request: Request, exc: Exception):
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rpc = RpcClient()


# Middleware for logging IP addresses
@app.middleware("http")
async def log_requests(request: Request, call_next):
    ip = request.client.host
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"IP Address: {ip}, Time: {current_time}")
    response = await call_next(request)
    return response


# Helper function for successful responses
def handle_rpc_response(result):
    # If result is a dictionary or list, we assume it’s a structured response.
    if isinstance(result, (dict, list)):
        return {
            "result": result,
            "error": None,
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
    # If result is an integer or other simple type, return directly in the response format.
    else:
        return {
            "result": result,
            "error": None,
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }

# Helper function for error responses
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
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code = 503, detail = "Service Unavailable. Try again later.")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code = 504,
                            detail = "Request Timeout. Service took too long to respond. Try again later.")
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code = 401,
                            detail = f"Oops! There was an HTTP error: {str(e)}. Check your request and try again.")
    except Exception as e:
        raise HTTPException(status_code = 500,
                            detail = "Oops! Looks like something broke. Either the universe just exploded, or you used the wrong API function. Try again, newb!")


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


# Information about a specific block
@app.get("/block/{hash}", summary="Get Block by Hash",
         description="Fetches the block information for a given block hash.")
async def get_block(hash: str):
    return rpc_call_wrapper(rpc.get_block, hash)


# Information about a specific block's hash by block number
@app.get("/blockhash/{block}", summary="Get Block Hash",
         description="Fetches the block hash for a specific block number.")
async def get_block_hash(block: int):
    return rpc_call_wrapper(rpc.get_block_hash, block)


# Current General Blockchain Stats
@app.get("/info")
async def get_info():
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

@app.get("/getpeers", summary="Get Filtered Peer List", description="Returns a list of peers filtered by DIVI Core version and block height.")
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



# Get address balance current and total received
@app.get("/getaddressbalance/{address}/{isVault}",
         summary="Get Address Balance",
         description="Fetches the current balance and total received amount for a specified address or vault owner key. Use the 'isVault' boolean to lookup a vault owner key.")
async def get_address_balance(address: str, isVault: str):
    isVaultBool = str_to_bool(isVault)
    return rpc_call_wrapper(rpc.get_address_balance, address, isVaultBool)


# Get address deltas (transaction history)
@app.get("/getaddressdeltas/{address}/{isVault}",
         summary="Get Address Transaction History (Deltas)",
         description="Returns the list of transaction deltas (history of transactions) for a specified address or vault owner key. This will include both spent and unspent transaction history. Use the 'isVault' boolean to lookup a vault owner key.")
async def get_address_deltas(address: str, isVault: str):
    isVaultBool = str_to_bool(isVault)
    return rpc_call_wrapper(rpc.get_address_deltas, address, isVaultBool)


# Get address transaction IDs (unspent transactions)
@app.get("/getaddresstxids/{address}/{isVault}",
         summary="Get Address or Vault Owner Key Transaction IDs",
         description="Fetches the list of transaction IDs associated with the specified address or vault owner key. This can include all transaction IDs, use the 'isVault' boolean to lookup a vault owner key.")
async def get_address_txids(address: str, isVault: str):
    isVaultBool = str_to_bool(isVault)
    return rpc_call_wrapper(rpc.get_address_txids, address, isVaultBool)


# Get address UTXOs for an address
@app.get("/getaddressutxos/{address}/{isVault}",
         summary="Get Address or Vault Owner Key UTXOs",
         description="Fetches the list of Unspent Transaction Outputs (UTXOs) associated with the specified address or vault owner key. Use the 'isVault' boolean to lookup a vault owner key.")
async def get_address_utxos(address: str, isVault: str):
    isVaultBool = str_to_bool(isVault)
    return rpc_call_wrapper(rpc.get_address_utxos, address, isVaultBool)


# Decode raw transaction
@app.get("/decode-raw-tx/{hex}",
         summary="Decode Raw Transaction",
         description="Decodes a raw transaction hex string and returns detailed information about the transaction, including inputs, outputs, and other metadata.")
async def decode_raw_transaction(hex: str):
    return rpc_call_wrapper(rpc.decode_raw_transaction, hex)


# Send raw transaction
@app.post("/sendrawtransaction",
          summary="Send Raw Transaction",
          description="Broadcasts a raw transaction to the blockchain network. The raw transaction must be provided as a hex string. Optionally, allow high fees.")
async def send_raw_transaction(hexstring: str, allowhighfees: bool = False):
    # Validate that hexstring is a non-empty string
    if not hexstring or not isinstance(hexstring, str):
        raise HTTPException(status_code=400, detail="Invalid hexstring provided")

    # Call the RPC client with the hexstring and allowhighfees
    return rpc_call_wrapper(rpc.send_raw_transaction, hexstring, allowhighfees)


# Get current mempool transactions
@app.get("/getrawmempool",
         summary="Get Current Mempool Transactions",
         description="Fetches the list of transaction IDs currently in the node's memory pool (mempool). These are unconfirmed transactions that are awaiting inclusion in the next block.")
async def get_raw_mempool():
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
    summary="Get Current Lottery Winners",
    description=(
            "Fetches the list of lottery candidates for a specific block if a block height is provided. "
            "If no block height is entered, it returns the current list of candidates. "
            "On the block where the lottery payout occurs, the list is purged."
    )
)
async def get_lottery(blockheight: Optional[int] = None):
    try:
        if blockheight is not None:
            # Blockheight provided, fetch for the specific block
            result = rpc.get_lottery_block_winners(blockheight)
        else:
            # No blockheight provided, fetch latest lottery winners
            result = rpc.get_lottery_block_winners()
        return handle_rpc_response(result)
    except Exception as e:
        return handle_rpc_error(str(e))


# Run app if executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config['host'], port=config['port'])