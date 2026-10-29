"""Seventh venue Meteora DBC: on-chain program and bonding-curve identity intake.

Program ID and PDA are from Meteora's published documentation. The
initial milestone authenticates the executable mainnet program, obtains
bounded active VirtualPool identity hints from read-only Solana RPC, and
retains raw program-owned source data for later official SDK/curve math.
No swap quotes, mint guesses, signing, registry admission or broadcast.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.orca_whirlpool import b58
PROGRAM="dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN"
POOL_AUTHORITY="FhVo3mqL8PW5pH5U2CN4XE33DokiyZnUwuGpH2hmHLuM"
UPGRADEABLE="BPFLoaderUpgradeab1e11111111111111111111111"
DISC=hashlib.sha256(b"account:VirtualPool").digest()[:8]
SAFE={"actionable":False,"broadcast":False,"native_pricing_verified":False,
      "official_sdk_parity_verified":False,"signed_parity_verified":False,
      "registry_admission_approved":False}

def capture(rpc,*,count=3):
    if type(count) is not int or not 1<=count<=6:
        raise ValueError("bounded DBC source identity count required")
    info=call(rpc,"getAccountInfo",[PROGRAM,{
        "encoding":"base64","commitment":"confirmed"}])
    program=info.get("value") if isinstance(info,dict) else None
    if (not isinstance(program,dict) or
            program.get("owner")!=UPGRADEABLE or
            program.get("executable") is not True):
        raise ValueError("seventh venue official Meteora DBC ELF not executable")
    encoded=program.get("data",[])
    if (not isinstance(encoded,list) or len(encoded)!=2
            or encoded[1]!="base64" or
            len(base64.b64decode(encoded[0],validate=True))!=36):
        raise ValueError("DBC program upgradeable metadata invalid")
    bytes_=base64.b64decode(encoded[0],validate=True)
    if int.from_bytes(bytes_[:4],"little")!=2:
        raise ValueError("DBC mainnet executable not upgradeable Program state")
    program_data=str(Pubkey.from_bytes(bytes_[4:36]))
    response=call(rpc,"getAccountInfo",[program_data,{
        "encoding":"base64","commitment":"confirmed"}])
    storage=response.get("value") if isinstance(response,dict) else None
    if (not isinstance(storage,dict) or storage.get("owner")!=UPGRADEABLE
            or storage.get("executable") is not False):
        raise ValueError("DBC upgradeable ProgramData missing or wrong owner")
    binary=base64.b64decode(storage["data"][0],validate=True)
    if len(binary)<49 or int.from_bytes(binary[:4],"little")!=3:
        raise ValueError("DBC ProgramData ELF header invalid")
    elf=binary[45:]
    if elf[:4]!=b"\x7fELF":
        raise ValueError("Meteora DBC real on-chain ELF missing")
    # getProgramAccounts is source-only discovery and may be disallowed
    # by a capped RPC provider. Never invent new pool identities.
    source_scan_status="ONCHAIN_PROGRAM_ACCOUNTS_REQUESTED"
    try:
        hints=call(rpc,"getProgramAccounts",[PROGRAM,{
        "encoding":"base64","commitment":"confirmed",
        "filters":[{"memcmp":{"offset":0,"bytes":b58(DISC)}}]}])
    except OSError:
        # This datasource rate-limits getProgramAccounts. The verified
        # original ELF remains useful; never fabricate discovered pools.
        hints=[]
        source_scan_status="SCAN_THROTTLED_NO_POOL_AUTHENTICATION"
    if not isinstance(hints,list):
        raise ValueError("DBC read-only active VirtualPool program account scan denied")
    accepted=[]
    for entry in hints:
        if not isinstance(entry,dict) or not isinstance(entry.get("account"),dict):
            continue
        account=entry["account"]
        if account.get("owner")!=PROGRAM or account.get("executable") is not False:
            continue
        raw=base64.b64decode(account["data"][0],validate=True)
        if raw[:8]!=DISC:continue
        address=entry.get("pubkey")
        if not isinstance(address,str):continue
        Pubkey.from_string(address)
        accepted.append({"address":address,"status":"DBC_PROGRAM_OWNED_VIRTUAL_POOL_SOURCE",
            "account_base64":account["data"][0],
            "account_sha256":hashlib.sha256(raw).hexdigest(),
            "account_lamports":account["lamports"]})
        if len(accepted)>=count:break
    return {"venue":"meteora_dbc","status":"SEVENTH_VENUE_READONLY_SOURCE_ONLY",
        "program":PROGRAM,"pool_authority":POOL_AUTHORITY,
        "onchain_elf_sha256":hashlib.sha256(elf).hexdigest(),
        "programdata_address":program_data,
        "source_pools":accepted,"authenticated":len(accepted),
        "scan_status":source_scan_status,**SAFE}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rpc",required=True)
    p.add_argument("--count",type=int,default=3)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    report=capture(args.rpc,count=args.count)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "authenticated":report["authenticated"],
                      "elf_sha256":report["onchain_elf_sha256"]}))
    if report["authenticated"]!=args.count and report["scan_status"]!="SCAN_THROTTLED_NO_POOL_AUTHENTICATION":
        raise SystemExit("Meteora DBC bounded real pool source target incomplete")
if __name__=="__main__":main()
