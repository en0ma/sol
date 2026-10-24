"""Single-attempt upstream RPC method diagnostic; never prints RPC URLs.

Compare a known direct pool read with one tightly filtered program scan,
both against the same configured upstream endpoint. No retries or swaps.
"""
import json,os
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM,SIZE
from arb.onchain_pool_discovery import MINTS

def probe(url,address):
    if not url.startswith(("https://","http://")):
        raise ValueError("RPC endpoint not configured")
    result={"diagnostic":"UPSTREAM_RPC_METHOD_COMPARISON",
            "provider_url_disclosed":False,"retries":0,
            "getAccountInfo":{"status":"NOT_ATTEMPTED"},
            "getProgramAccounts":{"status":"NOT_ATTEMPTED"}}
    try:
        value=call(url,"getAccountInfo",[address,{"encoding":"base64",
                        "commitment":"confirmed"}],timeout=25,retries=0)
        account=value.get("value")
        result["getAccountInfo"]={"status":"OK" if account else "EMPTY",
                                  "owner_matches_orca":bool(account and
                                                            account.get("owner")==PROGRAM)}
    except Exception as e:
        result["getAccountInfo"]={"status":"ERROR","kind":type(e).__name__,
                                  "rate_limited":("429" in str(e) or
                                                  "too many requests" in str(e).lower())}
    filters=[{"dataSize":SIZE},{"memcmp":{"offset":101,"bytes":MINTS["WSOL"]}},
             {"memcmp":{"offset":181,"bytes":MINTS["USDC"]}}]
    try:
        accounts=call(url,"getProgramAccounts",[PROGRAM,{"encoding":"base64",
                      "commitment":"confirmed","filters":filters}],
                      timeout=35,retries=0)
        result["getProgramAccounts"]={"status":"OK",
                                      "returned_accounts":len(accounts)}
    except Exception as e:
        result["getProgramAccounts"]={"status":"ERROR","kind":type(e).__name__,
                                      "rate_limited":("429" in str(e) or
                                                      "too many requests" in str(e).lower())}
    return result

def main():
    url=os.environ.get("SURFPOOL_DATASOURCE_RPC_URL")
    if not url:
        raise SystemExit("Missing upstream datasource")
    with open("arb/pool_registry.json") as file:
        address=next(p["address"] for p in json.load(file)["pools"]
                     if p["venue"]=="orca")
    result=probe(url,address)
    print(json.dumps(result,indent=2))
    output=os.environ.get("UPSTREAM_RPC_DIAGNOSTIC_REPORT")
    if output:
        with open(output,"w") as file:
            json.dump(result,file,indent=2)

if __name__=="__main__":
    main()
