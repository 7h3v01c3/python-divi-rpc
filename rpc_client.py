import requests
from requests.auth import HTTPBasicAuth
import logging
from config import RPC_URL, config


class RpcClient:
    def __init__(self):
        self.rpc_url = RPC_URL
        self.auth = HTTPBasicAuth(config['rpc_user'], config['rpc_password'])

    def call(self, method, params=None):
        params = params or []
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }
        headers = {'Content-Type': 'application/json'}

        # Add logging to debug the issue
        logging.info(f"Making RPC call to {self.rpc_url} with method: {method} and params: {params}")
        logging.info(f"Sending RPC request to {self.rpc_url}:")
        logging.info(f"Method: {method}, Params: {params}")
        logging.info(f"Raw Payload: {payload}")

        try:
            response = requests.post(self.rpc_url, headers=headers, json=payload, auth=self.auth)
            response.raise_for_status()
            logging.info(f"Response received: {response.status_code}, {response.text}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error occurred: {e}")
            raise Exception(f"Error occurred: {e}")

    # Address-related RPCs
    def get_address_balance(self, address, is_vault=False):
        return self.call('getaddressbalance', [{"addresses": [address]}, is_vault])

    def get_address_deltas(self, address, is_vault=False):
        return self.call('getaddressdeltas', [{"addresses": [address]}, is_vault])

    def get_address_txids(self, address, is_vault=False):
        return self.call('getaddresstxids', [{"addresses": [address]}, is_vault])

    def get_address_utxos(self, address, is_vault=False):
        return self.call('getaddressutxos', [{"addresses": [address]}, is_vault])

    # Block-related RPCs
    def get_block_count(self):
        return self.call('getblockcount')

    def get_block(self, block_hash, verbosity=True):
        return self.call('getblock', [block_hash, verbosity])

    def get_block_hash(self, block_number):
        return self.call('getblockhash', [block_number])

    # Transaction-related RPCs
    def get_raw_transaction(self, txid, verbose=True):
        """
        Fetch the raw transaction for the given txid.
        - verbose=True translates to 1 (for RPC call)
        - verbose=False translates to 0
        """
        verbose_value = 1 if verbose else 0  # Convert True to 1, False to 0
        return self.call('getrawtransaction', [txid, verbose_value])

    def send_raw_transaction(self, hexstring, allow_high_fees=False):
        return self.call('sendrawtransaction', [hexstring, allow_high_fees])

    def decode_raw_transaction(self, hexstring):
        return self.call('decoderawtransaction', [hexstring])

    # Network-related RPCs
    def get_connection_count(self):
        return self.call('getconnectioncount')

    # Info-related RPCs
    def get_info(self):
        return self.call('getinfo')

    # Get current mempool transactions
    def get_raw_mempool(self):
        return self.call('getrawmempool')

    # Get mempool info
    def get_mempool_info(self):
        return self.call('getmempoolinfo')

    # Lottery-related RPCs
    def get_lottery_block_winners(self, block_height=None):
        return self.call('getlotteryblockwinners', [block_height] if block_height else [])

    def ping(self):
        return {"message": "pong"}
