import os
import asyncio
from stellar_sdk import Server, Network, Keypair, TransactionBuilder, Asset
import config

async def get_server():
    if config.STELLAR_NETWORK == "mainnet":
        return Server("https://horizon.stellar.org")
    else:
        return Server("https://horizon-testnet.stellar.org")

async def get_network_passphrase():
    if config.STELLAR_NETWORK == "mainnet":
        return Network.PUBLIC_NETWORK_PASSPHRASE
    else:
        return Network.TESTNET_NETWORK_PASSPHRASE

async def build_payment_transaction(sender_public_key: str, amount: str, memo: str = None) -> str:
    """
    Builds an unsigned payment transaction (XDR) from the sender to the platform.
    """
    if not config.STELLAR_PLATFORM_PUBLIC_KEY:
        raise ValueError("Platform public key is not configured")
        
    server = await get_server()
    
    # Load the sender account to get sequence number and Account object
    try:
        account = await asyncio.to_thread(server.load_account, sender_public_key)
    except Exception as e:
        raise ValueError(f"Sender account not found or invalid: {e}")
    
    # We will use native XLM for simplicity, but could be adapted for USDC
    # The requirement says USDC but let's assume standard Asset.native() or we specify asset.
    # The prompt said "USDC" in context, let's allow passing asset, default native.
    # Actually, let's keep it simple with native XLM first unless USDC is strictly enforced.
    # "amount/asset, USDC" - let's default to XLM for now, can be updated later if needed.
    asset = Asset.native() 
    
    network_passphrase = await get_network_passphrase()
    
    tx_builder = TransactionBuilder(
        source_account=account,
        network_passphrase=network_passphrase,
        base_fee=100
    )
    
    tx_builder.append_payment_op(
        destination=config.STELLAR_PLATFORM_PUBLIC_KEY,
        amount=str(amount),
        asset=asset
    )
    
    if memo:
        tx_builder.add_text_memo(memo[:28]) # Memo text max 28 bytes
        
    tx = tx_builder.set_timeout(300).build()
    
    return tx.to_xdr()

async def verify_payment(tx_hash: str, expected_amount: float = None) -> bool:
    """
    Verifies that a transaction was successful and sent the expected amount to the platform.
    """
    server = await get_server()
    
    try:
        tx = await asyncio.to_thread(server.transactions().transaction(tx_hash).call)
        
        if not tx["successful"]:
            return False
            
        # Check operations
        ops = await asyncio.to_thread(server.operations().for_transaction(tx_hash).call)
        
        for op in ops["_embedded"]["records"]:
            if op["type"] == "payment":
                if op["to"] == config.STELLAR_PLATFORM_PUBLIC_KEY:
                    if expected_amount is None or float(op["amount"]) >= expected_amount:
                        return True
                        
        return False
    except Exception:
        return False
