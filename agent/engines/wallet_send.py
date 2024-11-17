
import os
import re
import requests
from web3 import Web3
from ens import ENS
from engines.prompts import get_wallet_decision_prompt

def get_wallet_balance(private_key, eth_mainnet_rpc_url):
    w3 = Web3(Web3.HTTPProvider(eth_mainnet_rpc_url))
    public_address = w3.eth.account.from_key(private_key).address

    # Retrieve and print the balance of the account in Ether
    balance_wei = w3.eth.get_balance(public_address)
    balance_ether = w3.from_wei(balance_wei, 'ether')

    return balance_ether

def get_erc20_balance(private_key, eth_mainnet_rpc_url, erc20_address):
    w3 = Web3(Web3.HTTPProvider(eth_mainnet_rpc_url))
    public_address = w3.eth.account.from_key(private_key).address

    # ERC20 ABI for balanceOf function
    ERC20_ABI = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf", 
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        }
    ]

    # Create contract instance
    token_contract = w3.eth.contract(
        address=Web3.to_checksum_address(erc20_address),
        abi=ERC20_ABI
    )

    # Get token balance
    balance = token_contract.functions.balanceOf(public_address).call()
    return balance


def transfer_erc20(private_key, eth_mainnet_rpc_url, to_address, erc20_address, amount_of_tokens):
    """
    Transfers ERC20 tokens from one account to another.

    Parameters:
    - private_key (str): The private key of the sender's Ethereum account in hex format.
    - mainnet RPC (str): A useable mainnet RPC URL
    - to_address (str): The Ethereum address or ENS name of the recipient.
    - erc20_address (str): The ERC20 token contract address
    - amount_of_tokens (int): Amount of tokens to transfer (in token base units)

    Returns:
    - str: The transaction hash as a hex string if the transaction was successful.
    - str: "Transaction failed" or an error message if the transaction was not successful or an error occurred.
    """
    try:
        w3 = Web3(Web3.HTTPProvider(eth_mainnet_rpc_url))

        # Check if connected to blockchain
        if not w3.is_connected():
            print("Failed to connect to ETH Mainnet")
            return "Connection failed"

        # Set up ENS
        w3.ens = ENS.fromWeb3(w3)

        # Resolve ENS name to Ethereum address if necessary
        if Web3.is_address(to_address):
            # The to_address is a valid Ethereum address
            resolved_address = Web3.to_checksum_address(to_address)
        else:
            # Try to resolve as ENS name
            resolved_address = w3.ens.address(to_address)
            if resolved_address is None:
                return f"Could not resolve ENS name: {to_address}"

        print(f"Transferring to {resolved_address}")

        # Get the public address from the private key
        account = w3.eth.account.from_key(private_key)
        public_address = account.address

        # ERC20 token contract ABI - need transfer and balanceOf functions
        ERC20_ABI = [
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }
        ]

        # Create contract instance
        token_contract = w3.eth.contract(
            address=Web3.to_checksum_address(erc20_address),
            abi=ERC20_ABI
        )

        # Check token balance
        token_balance = token_contract.functions.balanceOf(public_address).call()
        if token_balance < amount_of_tokens:
            return f"Insufficient token balance. Available: {token_balance}, Required: {amount_of_tokens}"

        # Get the nonce for the transaction
        nonce = w3.eth.get_transaction_count(public_address)

        # Build the transaction
        transaction = token_contract.functions.transfer(
            resolved_address,
            amount_of_tokens
        ).build_transaction({
            'from': public_address,
            'gas': 100000,  # Estimated gas, may need adjustment for different tokens
            'gasPrice': int(w3.eth.gas_price * 1.1),
            'nonce': nonce,
            'chainId': 1  # Mainnet chain ID
        })

        # Sign the transaction
        signed_txn = w3.eth.account.sign_transaction(transaction, private_key=private_key)

        # Send the transaction
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

        # Wait for the transaction receipt
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        # Check the status of the transaction
        if tx_receipt['status'] == 1:
            return tx_hash.hex()
        else:
            return "Transaction failed"
    except Exception as e:
        return f"An error occurred: {e}"

def transfer_eth(private_key, eth_mainnet_rpc_url, to_address, amount_in_ether):
    """
    Transfers Ethereum from one account to another.

    Parameters:
    - private_key (str): The private key of the sender's Ethereum account in hex format.
    - to_address (str): The Ethereum address or ENS name of the recipient.
    - amount_in_ether (float): The amount of Ether to send.

    Returns:
    - str: The transaction hash as a hex string if the transaction was successful.
    - str: "Transaction failed" or an error message if the transaction was not successful or an error occurred.
    """
    try:
        w3 = Web3(Web3.HTTPProvider(eth_mainnet_rpc_url))

        # Check if connected to blockchain
        if not w3.is_connected():
            print("Failed to connect to ETH Mainnet")
            return "Connection failed"

        # Set up ENS
        w3.ens = ENS.fromWeb3(w3)

        # Resolve ENS name to Ethereum address if necessary
        if Web3.is_address(to_address):
            # The to_address is a valid Ethereum address
            resolved_address = Web3.to_checksum_address(to_address)
        else:
            # Try to resolve as ENS name
            resolved_address = w3.ens.address(to_address)
            if resolved_address is None:
                return f"Could not resolve ENS name: {to_address}"

        print(f"Transferring to {resolved_address}")

        # Convert the amount in Ether to Wei
        amount_in_wei = w3.toWei(amount_in_ether, 'ether')

        # Get the public address from the private key
        account = w3.eth.account.from_key(private_key)
        public_address = account.address

        # Get the nonce for the transaction
        nonce = w3.eth.get_transaction_count(public_address)

        # Build the transaction
        transaction = {
            'to': resolved_address,
            'value': amount_in_wei,
            'gas': 21000,
            'gasPrice': int(w3.eth.gas_price * 1.1),
            'nonce': nonce,
            'chainId': 1  # Mainnet chain ID
        }

        # Sign the transaction
        signed_txn = w3.eth.account.sign_transaction(transaction, private_key=private_key)

        # Send the transaction
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

        # Wait for the transaction receipt
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        # Check the status of the transaction
        if tx_receipt['status'] == 1:
            return tx_hash.hex()
        else:
            return "Transaction failed"
    except Exception as e:
        return f"An error occurred: {e}"

def wallet_address_in_post(posts, private_key, eth_mainnet_rpc_url: str,llm_api_key: str):
    """
    Detects wallet addresses or ENS domains from a list of posts.
    Converts all items to strings first, then checks for matches.

    Parameters:
    - posts (List): List of posts of any type

    Returns:
    - List[Dict]: List of dicts with 'address' and 'amount' keys
    """

    # Convert everything to strings first
    str_posts = [str(post) for post in posts]
    
    # Then look for matches in all the strings
    eth_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b|\b\S+\.eth\b')
    matches = []
    
    for post in str_posts:
        found_matches = eth_pattern.findall(post)
        matches.extend(found_matches)
    
    wallet_balance = get_wallet_balance(private_key, eth_mainnet_rpc_url)
    prompt = get_wallet_decision_prompt(posts, matches, wallet_balance)
    
    response = requests.post(
        url="https://api.hyperbolic.xyz/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {llm_api_key}",
        },
        json={
            "messages": [
                {
                    "role": "system",
        	        "content": prompt
                },
                {
                    "role": "user",
                    "content": "Respond only with the wallet address(es) and amount(s) you would like to send to."
                }
            ],
            "model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
            "presence_penalty": 0,
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 40,
        }
    )
    
    if response.status_code == 200:
        print(f"ETH Addresses and amounts chosen from Posts: {response.json()}")
        return response.json()['choices'][0]['message']['content']
    else:
        raise Exception(f"Error generating short-term memory: {response.text}")

def erc20_instructions_in_post(posts, private_key, eth_mainnet_rpc_url: str, llm_api_key: str, erc20_address: str):
    """
    Detects wallet addresses or ENS domains from a list of posts and decides whether to transfer ERC20 tokens.
    Converts all items to strings first, then checks for matches.

    Parameters:
    - posts (List): List of posts of any type
    - private_key (str): Private key for wallet
    - eth_mainnet_rpc_url (str): Ethereum RPC URL
    - llm_api_key (str): API key for LLM service
    - erc20_address (str): Address of ERC20 token contract

    Returns:
    - List[Dict]: List of dicts with 'address' and 'amount' keys
    """

    # Convert everything to strings first
    str_posts = [str(post) for post in posts]
    
    # Then look for matches in all the strings
    eth_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b|\b\S+\.eth\b')
    matches = []
    
    for post in str_posts:
        found_matches = eth_pattern.findall(post)
        matches.extend(found_matches)
    
    wallet_balance = get_wallet_balance(private_key, eth_mainnet_rpc_url, erc20_address)
    prompt = get_wallet_decision_prompt(posts, matches, wallet_balance)
    
    response = requests.post(
        url="https://api.hyperbolic.xyz/v1/chat/completions",
        headers={
            "Content-Type": "application/json", 
            "Authorization": f"Bearer {llm_api_key}",
        },
        json={
            "messages": [
                {
                    "role": "system",
                    "content": prompt + "\nYou are deciding whether to transfer ERC20 tokens. Consider token balance and transaction costs."
                },
                {
                    "role": "user", 
                    "content": "Respond only with the wallet address(es), ERC20 address and token amount(s) you would like to send to. If you decide not to transfer, respond with 'NO_TRANSFER'."
                }
            ],
            "model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
            "presence_penalty": 0,
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 40,
        }
    )
    
    if response.status_code == 200:
        llm_response = response.json()['choices'][0]['message']['content']
        print(f"LLM decision for ERC20 transfers: {llm_response}")
        
        if llm_response == "NO_TRANSFER":
            return None
            
        return llm_response
    else:
        raise Exception(f"Error getting LLM decision: {response.text}")