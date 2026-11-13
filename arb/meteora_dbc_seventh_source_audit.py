"""Independent post-hoc DBC source-only audit of original contextual raw bytes.

This is NOT a native integer quote, SDK parity, signed swap or permission to
broadcast. Original onchain owner and role bytes are reconciled from a single
saved confirmed source snapshot, separately from the capture implementation.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from solders.pubkey import Pubkey

PROGRAM="dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN"
TOKEN_PROGRAM="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022="TokenzQdBNbLqP5VEhdkAS6EPFTEwJyR9E3weuAF"
SYSVAR="Sysvar1111111111111111111111111111111111111"
CLOCK="SysvarC1ock11111111111111111111111111111111"
AUTHORITY="FhVo3mqL8PW5pH5U2CN4XE33DokiyZnUwuGpH2hmHLuM"
POOL_DISC=hashlib.sha256(b"account:VirtualPool").digest()[:8]
CFG_DISC=hashlib.sha256(b"account:PoolConfig").digest()[:8]


def pub(raw):
    return str(Pubkey.from_bytes(raw))


def independently_audit(report):
    if (not isinstance(report,dict)
            or report.get("status")!="DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED"
            or report.get("actionable") is not False
            or report.get("broadcast") is not False
            or report.get("signed_parity_verified") is not False
            or not isinstance(report.get("source_pools"),list)
            or not 1<=len(report["source_pools"])<=6):
        raise ValueError("DBC original unsigned source report required")
    seen=set();audited=[]
    for row in report["source_pools"]:
        address=row["pool"]
        if address in seen:raise ValueError("DBC source duplicate pool")
        seen.add(address)
        accounts=row["accounts"];fields=row["pool_fields"]
        roles=[address,fields["config"],fields["base_mint"],
               fields["base_vault"],fields["quote_vault"],CLOCK]
        if set(accounts)!=set(roles) or len(set(roles))!=6:
            raise ValueError("DBC account provenance roles incomplete")
        raw={}
        for role in roles:
            entry=accounts[role]
            if (entry.get("executable") is not False
                    or type(entry.get("lamports")) is not int
                    or entry["lamports"]<0):
                raise ValueError("DBC original account metadata invalid")
            data=base64.b64decode(entry["account_base64"],validate=True)
            if base64.b64encode(data).decode()!=entry["account_base64"]:
                raise ValueError("DBC source raw base64 not canonical")
            if hashlib.sha256(data).hexdigest()!=entry.get("sha256"):
                raise ValueError("DBC source digest mismatch")
            raw[role]=data
        pool=raw[address];cfg=raw[fields["config"]]
        if (len(pool)!=424 or pool[:8]!=POOL_DISC
                or len(cfg)<40 or cfg[:8]!=CFG_DISC
                or accounts[address]["owner"]!=PROGRAM
                or accounts[fields["config"]]["owner"]!=PROGRAM):
            raise ValueError("DBC original pool/config owner or discriminator mismatch")
        expected={
          "config":pub(pool[72:104]),
          "creator":pub(pool[104:136]),
          "base_mint":pub(pool[136:168]),
          "base_vault":pub(pool[168:200]),
          "quote_vault":pub(pool[200:232]),
          "base_reserve":int.from_bytes(pool[232:240],"little"),
          "quote_reserve":int.from_bytes(pool[240:248],"little"),
          "sqrt_price_q64":int.from_bytes(pool[280:296],"little"),
          "pool_type":pool[304],"is_migrated":pool[305],
          "migration_progress":pool[308],"quote_mint":pub(cfg[8:40])
        }
        if any(fields.get(k)!=v for k,v in expected.items()):
            raise ValueError("DBC independently decoded PoolState/config disagreement")
        if (fields["pool_type"] not in (0,1) or fields["is_migrated"]!=0
                or fields["migration_progress"]!=0 or fields["sqrt_price_q64"]==0):
            raise ValueError("DBC original source is not active standard VirtualPool")
        base_mint_owner=accounts[fields["base_mint"]]["owner"]
        if base_mint_owner not in (TOKEN_PROGRAM,TOKEN_2022):
            raise ValueError("DBC base mint owner not SPL/Token-2022")
        if accounts[fields["base_vault"]]["owner"]!=base_mint_owner:
            raise ValueError("DBC base vault token program disagreement")
        if accounts[fields["quote_vault"]]["owner"] not in (TOKEN_PROGRAM,TOKEN_2022):
            raise ValueError("DBC quote vault owner not SPL/Token-2022")
        if len(raw[fields["base_mint"]])<82:
            raise ValueError("DBC original base mint truncated")
        for vault,mint in ((fields["base_vault"],fields["base_mint"]),
                            (fields["quote_vault"],fields["quote_mint"])):
            b=raw[vault]
            if (len(b)<165 or pub(b[:32])!=mint or pub(b[32:64])!=AUTHORITY):
                raise ValueError("DBC original token vault mint/authority mismatch")
        clock=raw[CLOCK]
        if (len(clock)!=40 or accounts[CLOCK]["owner"]!=SYSVAR
                or int.from_bytes(clock[:8],"little")!=row["clock_slot"]
                or int.from_bytes(clock[32:40],"little",signed=True)!=row["clock_unix_timestamp"]
                or row["clock_slot"]>row["source_slot"]):
            raise ValueError("DBC original Clock inconsistent")
        audited.append({"pool":address,"source_slot":row["source_slot"],
             "pool_sha256":accounts[address]["sha256"],
             "original_spl_source_authenticated":True,
             "native_pricing_verified":False,"signed_swap_verified":False})
    return {"status":"INDEPENDENT_DBC_ORIGINAL_SOURCE_ONLY_NOT_SIGNED",
       "authenticated_source_pools":len(audited),"pools":audited,
       "native_pricing_verified":False,"official_sdk_parity_verified":False,
       "signed_parity_verified":False,"registry_admission_approved":False,
       "actionable":False,"broadcast":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    r=independently_audit(json.loads(Path(a.source).read_text()))
    Path(a.output).write_text(json.dumps(r,indent=2)+"\n")
    print(json.dumps({"status":r["status"],
      "authenticated_source_pools":r["authenticated_source_pools"],
      "signed_verified_pools":0}))


if __name__=="__main__":
    main()
