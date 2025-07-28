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

processed_deposits = set()
processed_unwraps = set()

def scan_blocks(chain, contract_info="contract_info.json"):
    """
        chain - (string) should be either "source" or "destination"
        Scan the last 5 blocks of the source and destination chains
        Look for 'Deposit' events on the source chain and 'Unwrap' events on the destination chain
        When Deposit events are found on the source chain, call the 'wrap' function the destination chain
        When Unwrap events are found on the destination chain, call the 'withdraw' function on the source chain
    """
    global processed_deposits, processed_unwraps

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
    start_block = latest_block - 15  # Even more blocks
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
            # Get all deposit events in one call
            deposit_events = contract.events.Deposit().get_logs(
                from_block=start_block,
                to_block=end_block
            )

            print(f"Found {len(deposit_events)} Deposit events")

            for i, event in enumerate(deposit_events):
                # Create unique ID for event to avoid processing twice
                event_id = f"{event.transactionHash.hex()}-{event.logIndex}"
                if event_id in processed_deposits:
                    print(f"Skipping already processed deposit {event_id}")
                    continue
                
                processed_deposits.add(event_id)
                
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

        # For destination chain, if we can't scan events due to rate limiting,
        # let's try a different approach - check recent blocks one by one with long delays
        
        unwrap_events = []
        
        # Try scanning recent blocks one by one with very long delays
        print("Attempting block-by-block scan with extended delays...")
        
        for block_offset in range(5):  # Only check last 5 blocks
            block_num = latest_block - block_offset
            try:
                print(f"Checking block {block_num}...")
                time.sleep(8)  # 8 second delay between each block
                
                events = contract.events.Unwrap().get_logs(
                    from_block=block_num,
                    to_block=block_num
                )
                
                for event in events:
                    event_id = f"{event.transactionHash.hex()}-{event.logIndex}"
                    if event_id not in processed_unwraps:
                        unwrap_events.append(event)
                        processed_unwraps.add(event_id)
                
                if events:
                    print(f"Found {len(events)} events in block {block_num}")
                    
            except Exception as block_e:
                print(f"Error scanning block {block_num}: {block_e}")
                time.sleep(15)  # Longer delay on error
                continue

        print(f"Found {len(unwrap_events)} Unwrap events total")

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
                # Long delay before each withdraw transaction
                time.sleep(10)
                
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
                    time.sleep(10)

            except Exception as e:
                print(f"Error sending withdraw transaction: {e}")

    return 1