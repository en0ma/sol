"""On-chain program registry for DEX venue coverage and explicit capability gates.

'program_verified' DOES NOT imply a pool is decoded, quoted, or tradable.
Unsupported pool layouts must not be silently interpreted as Orca/Raydium.
"""
import json,os
from arb.rpc import inspect_account
from arb.fork_probe import PROGRAMS, UPGRADEABLE_LOADER

# All known on-chain programs already verified by the fork probe.
PROGRAM_VENUES={
  "Meteora DLMM":"meteora_dlmm",
  "Raydium CLMM":"raydium_clmm",
  "Raydium CPMM":"raydium_cpmm",
  "Meteora DAMM v2":"meteora_damm_v2",
  "Orca Whirlpools":"orca",
}
EXECUTABLE={"orca","raydium_cpmm"}

def probe(rpc):
    results={}
    for name, address in PROGRAMS.items():
        account=inspect_account(rpc,address,UPGRADEABLE_LOADER)
        available=(account.get("exists") is True and account.get("executable") is True
                   and account.get("owner_matches") is True)
        venue=PROGRAM_VENUES[name]
        results[venue]={"program":address,"program_verified":available,
             "pool_decoder_available":venue in EXECUTABLE,
             "swap_simulator_available":venue in EXECUTABLE,
             "pool_verified":False,
             "status":("READY_FOR_POOL_VALIDATION" if available and venue in EXECUTABLE
                else "PROGRAM_ONLY" if available else "PROGRAM_UNAVAILABLE")}
    return {"venues":results,"rpc_only":True,"new_swap_execution_demonstrated":False}

def main():
    report=probe(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"))
    print(json.dumps(report,indent=2))
    output=os.environ.get("DEX_VENUE_REPORT")
    if output:
        with open(output,"w") as f:json.dump(report,f,indent=2)
    return 0 if all(x["program_verified"] for x in report["venues"].values()) else 1
if __name__=="__main__":raise SystemExit(main())
