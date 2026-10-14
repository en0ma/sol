"""Execute a *simulated* System Program transfer against Surfpool.

This proves the fork can process a serialized transaction. It does NOT exercise
AMM swap instructions, validate routing, or send funds to mainnet.
"""
import json
import os
from arb.rpc import call

def main():
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.system_program import transfer, TransferParams
    from solders.message import Message
    from solders.transaction import Transaction
    from solders.hash import Hash

    rpc = os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899")
    payer = Keypair()
    receiver = Keypair().pubkey()
    result = call(rpc, "requestAirdrop", [str(payer.pubkey()), 1_000_000_000])
    if not isinstance(result, str):
        raise RuntimeError("Surfpool did not confirm airdrop request")
    # Surfpool --ci operates on a local ephemeral ledger.
    import time
    for _ in range(40):
        balance = call(rpc, "getBalance", [str(payer.pubkey())])["value"]
        if balance >= 1_000_000_000:
            break
        time.sleep(0.25)
    else:
        raise RuntimeError("Local Surfpool airdrop not reflected")
    hash_value = call(rpc, "getLatestBlockhash")["value"]["blockhash"]
    ix = transfer(TransferParams(from_pubkey=payer.pubkey(),
                                 to_pubkey=receiver, lamports=1000))
    tx = Transaction.new_signed_with_payer([ix], payer.pubkey(), [payer], Hash.from_string(hash_value))
    import base64
    wire = base64.b64encode(bytes(tx)).decode("ascii")
    output = call(rpc, "simulateTransaction", [wire, {
        "encoding": "base64", "sigVerify": True,
        "commitment": "processed"
    }])
    value = output.get("value", {})
    summary = {"transaction_type": "local-only system transfer",
               "err": value.get("err"), "unitsConsumed": value.get("unitsConsumed"),
               "logs": value.get("logs", [])}
    print(json.dumps(summary, indent=2))
    if value.get("err") is not None:
        raise SystemExit("Transaction simulation failed")
    if not isinstance(value.get("unitsConsumed"), int):
        raise SystemExit("Simulation missing compute usage")

if __name__ == "__main__":
    main()
