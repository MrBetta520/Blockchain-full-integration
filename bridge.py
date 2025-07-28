from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import json
import pandas as pd
import time


def connect_to(chain):
    if chain == 'source':  # The source contract chain is avax
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc" #AVAX C-chain testnet

    if chain == 'destination':  # The destination contract chain is bsc
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/" #BSC testnet

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    """
        Load the contract_info file into a dictionary
        This function is used by the autograder and will likely be useful to you
    """
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]



def scan_blocks(chain, contract_info="contract_info.json"):
    """
        chain - (string) should be either "source" or "destination"
        Scan the last 5 blocks of the source and destination chains
        Look for 'Deposit' events on the source chain and 'Unwrap' events on the destination chain
        When Deposit events are found on the source chain, call the 'wrap' function the destination chain
        When Unwrap events are found on the destination chain, call the 'withdraw' function on the source chain
    """

    # This is different from Bridge IV where chain was "avax" or "bsc"
    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return 0
    
        #YOUR CODE HERE
    time.sleep(5)
    
    w3 = connect_to(chain)

    contract_data = get_contract_info(chain, contract_info)
    if not contract_data:
        return 0

    contract_address = contract_data['address']
    contract_abi = contract_data['abi']
    contract = w3.eth.contract(address=contract_address, abi=contract_abi)

    latest_block = w3.eth.get_block_number()
    start_block = latest_block - 4
    end_block = latest_block

    print(f"Scanning blocks {start_block} to {end_block} on {chain} chain")

    if chain == 'source':
        dest_w3 = connect_to('destination')
        dest_contract_data = get_contract_info('destination', contract_info)
        dest_contract = dest_w3.eth.contract(
            address=dest_contract_data['address'],
            abi=dest_contract_data['abi']
        )

        try:
            # Long delay before scanning
            time.sleep(3)
            
            # Try scanning block by block to avoid rate limits
            deposit_events = []
            for block_num in range(start_block, end_block + 1):
                try:
                    events = contract.events.Deposit().get_logs(
                        from_block=block_num,
                        to_block=block_num
                    )
                    deposit_events.extend(events)
                    time.sleep(1)  # Delay between block scans
                except Exception as block_e:
                    print(f"Error scanning block {block_num}: {block_e}")
                    continue

            print(f"Found {len(deposit_events)} Deposit events")

            for i, event in enumerate(deposit_events):
                token = event.args['token']
                recipient = event.args['recipient']
                amount = event.args['amount']

                print(f"Processing Deposit {i+1}: token={token}, recipient={recipient}, amount={amount}")

                warden_key = dest_contract_data.get('warden_key')
                if not warden_key:
                    print("Error: No warden key found in destination contract info")
                    continue

                warden_account = dest_w3.eth.account.from_key(warden_key)

                try:
                    # Long delay between transactions
                    if i > 0:
                        time.sleep(10)
                    
                    # Get current gas price and add buffer
                    current_gas_price = dest_w3.eth.gas_price
                    buffered_gas_price = int(current_gas_price * 1.5)  # 50% buffer
                    
                    # Get fresh nonce
                    nonce = dest_w3.eth.get_transaction_count(warden_account.address)
                    
                    wrap_txn = dest_contract.functions.wrap(
                        token,
                        recipient,
                        amount
                    ).build_transaction({
                        'from': warden_account.address,
                        'nonce': nonce,
                        'gas': 500000,  # High gas limit
                        'gasPrice': buffered_gas_price,
                    })

                    signed_txn = dest_w3.eth.account.sign_transaction(wrap_txn, warden_key)
                    tx_hash = dest_w3.eth.send_raw_transaction(signed_txn.raw_transaction)

                    print(f"Wrap transaction sent: {tx_hash.hex()}")
                    
                    # Long wait for confirmation
                    time.sleep(8)

                except Exception as e:
                    print(f"Error sending wrap transaction: {e}")

        except Exception as e:
            print(f"Error scanning for Deposit events: {e}")

    elif chain == 'destination':
        src_w3 = connect_to('source')
        src_contract_data = get_contract_info('source', contract_info)
        src_contract = src_w3.eth.contract(
            address=src_contract_data['address'],
            abi=src_contract_data['abi']
        )

        try:
            # Very long delay to avoid rate limiting
            time.sleep(10)
            
            # Try scanning with smaller block ranges and longer delays
            unwrap_events = []
            
            # Scan block by block with delays
            for block_num in range(start_block, end_block + 1):
                try:
                    time.sleep(2)  # Delay before each block scan
                    events = contract.events.Unwrap().get_logs(
                        from_block=block_num,
                        to_block=block_num
                    )
                    unwrap_events.extend(events)
                    
                except Exception as block_e:
                    print(f"Error scanning block {block_num}: {block_e}")
                    # Try with even longer delay on error
                    time.sleep(5)
                    continue

            print(f"Found {len(unwrap_events)} Unwrap events")

            for i, event in enumerate(unwrap_events):
                underlying_token = event.args['underlying_token']
                to_address = event.args['to']
                amount = event.args['amount']

                print(f"Processing Unwrap {i+1}: token={underlying_token}, to={to_address}, amount={amount}")

                warden_key = src_contract_data.get('warden_key')
                if not warden_key:
                    print("Error: No warden key found in source contract info")
                    continue

                warden_account = src_w3.eth.account.from_key(warden_key)

                try:
                    # Very long delay between transactions
                    time.sleep(15)
                    
                    # Get current gas price and add buffer
                    current_gas_price = src_w3.eth.gas_price
                    buffered_gas_price = int(current_gas_price * 1.5)  # 50% buffer
                    
                    # Get fresh nonce
                    nonce = src_w3.eth.get_transaction_count(warden_account.address)
                    
                    withdraw_txn = src_contract.functions.withdraw(
                        underlying_token,
                        to_address,
                        amount
                    ).build_transaction({
                        'from': warden_account.address,
                        'nonce': nonce,
                        'gas': 500000,  # High gas limit
                        'gasPrice': buffered_gas_price,
                    })

                    signed_txn = src_w3.eth.account.sign_transaction(withdraw_txn, warden_key)
                    tx_hash = src_w3.eth.send_raw_transaction(signed_txn.raw_transaction)

                    print(f"Withdraw transaction sent: {tx_hash.hex()}")
                    
                    # Long wait for confirmation
                    time.sleep(10)

                except Exception as e:
                    print(f"Error sending withdraw transaction: {e}")

        except Exception as e:
            print(f"Error scanning for Unwrap events: {e}")

    return 1