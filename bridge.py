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
    w3 = connect_to(chain)

    contract_data = get_contract_info(chain, contract_info)
    if not contract_data:
        return 0

    contract_address = contract_data['address']
    contract_abi = contract_data['abi']
    contract = w3.eth.contract(address=contract_address, abi=contract_abi)

    latest_block = w3.eth.get_block_number()
    # Scan more blocks to catch all events
    start_block = latest_block - 10  # Increased from 4 to 10
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
            # Get all deposit events in one call - more efficient
            deposit_events = contract.events.Deposit().get_logs(
                from_block=start_block,
                to_block=end_block
            )

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
                    # Get fresh nonce each time
                    nonce = dest_w3.eth.get_transaction_count(warden_account.address)
                    
                    # Use estimated gas instead of fixed amount
                    try:
                        gas_estimate = dest_contract.functions.wrap(
                            token, recipient, amount
                        ).estimate_gas({'from': warden_account.address})
                        gas_limit = int(gas_estimate * 1.2)  # 20% buffer
                    except:
                        gas_limit = 200000  # Fallback
                    
                    # Get current gas price
                    gas_price = dest_w3.eth.gas_price
                    
                    wrap_txn = dest_contract.functions.wrap(
                        token,
                        recipient,
                        amount
                    ).build_transaction({
                        'from': warden_account.address,
                        'nonce': nonce,
                        'gas': gas_limit,
                        'gasPrice': gas_price,
                    })

                    signed_txn = dest_w3.eth.account.sign_transaction(wrap_txn, warden_key)
                    tx_hash = dest_w3.eth.send_raw_transaction(signed_txn.raw_transaction)

                    print(f"Wrap transaction sent: {tx_hash.hex()}")
                    
                    # Wait for transaction to be mined
                    receipt = dest_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                    print(f"Wrap transaction confirmed in block {receipt.blockNumber}")

                    # Add delay between transactions to avoid nonce issues
                    if i < len(deposit_events) - 1:
                        time.sleep(5)

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

        # Add a longer delay before scanning destination chain to let transactions settle
        time.sleep(10)

        try:
            # Try multiple approaches to get events, with increasing delays
            unwrap_events = []
            
            # First try: normal range scan
            try:
                unwrap_events = contract.events.Unwrap().get_logs(
                    from_block=start_block,
                    to_block=end_block
                )
            except Exception as first_e:
                print(f"First attempt failed: {first_e}")
                time.sleep(15)
                
                # Second try: smaller range
                try:
                    mid_block = start_block + (end_block - start_block) // 2
                    events1 = contract.events.Unwrap().get_logs(
                        from_block=start_block,
                        to_block=mid_block
                    )
                    time.sleep(10)
                    events2 = contract.events.Unwrap().get_logs(
                        from_block=mid_block + 1,
                        to_block=end_block
                    )
                    unwrap_events = events1 + events2
                except Exception as second_e:
                    print(f"Second attempt failed: {second_e}")
                    time.sleep(20)
                    
                    # Third try: latest blocks only
                    try:
                        recent_start = end_block - 5
                        unwrap_events = contract.events.Unwrap().get_logs(
                            from_block=recent_start,
                            to_block=end_block
                        )
                    except Exception as third_e:
                        print(f"All attempts failed: {third_e}")
                        unwrap_events = []

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
                    # Get fresh nonce
                    nonce = src_w3.eth.get_transaction_count(warden_account.address)
                    
                    # Use estimated gas
                    try:
                        gas_estimate = src_contract.functions.withdraw(
                            underlying_token, to_address, amount
                        ).estimate_gas({'from': warden_account.address})
                        gas_limit = int(gas_estimate * 1.2)  # 20% buffer
                    except:
                        gas_limit = 200000  # Fallback
                    
                    # Get current gas price
                    gas_price = src_w3.eth.gas_price
                    
                    withdraw_txn = src_contract.functions.withdraw(
                        underlying_token,
                        to_address,
                        amount
                    ).build_transaction({
                        'from': warden_account.address,
                        'nonce': nonce,
                        'gas': gas_limit,
                        'gasPrice': gas_price,
                    })

                    signed_txn = src_w3.eth.account.sign_transaction(withdraw_txn, warden_key)
                    tx_hash = src_w3.eth.send_raw_transaction(signed_txn.raw_transaction)

                    print(f"Withdraw transaction sent: {tx_hash.hex()}")
                    
                    # Wait for transaction to be mined
                    receipt = src_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                    print(f"Withdraw transaction confirmed in block {receipt.blockNumber}")

                    # Add delay between transactions
                    if i < len(unwrap_events) - 1:
                        time.sleep(5)

                except Exception as e:
                    print(f"Error sending withdraw transaction: {e}")

        except Exception as e:
            print(f"Error scanning for Unwrap events: {e}")

    return 1