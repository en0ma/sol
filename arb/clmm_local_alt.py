"""Provision address lookup tables ONLY against localhost Surfpool."""
import base64,time
from urllib.parse import urlparse
from arb.rpc import call
from arb.clmm_v0 import ALT_PROGRAM,load_table

def require_local(rpc):
    u=urlparse(rpc)
    if u.scheme!="http" or u.hostname not in ("localhost","127.0.0.1","::1") or u.username or u.password:
        raise ValueError("ALT mutation forbidden outside local Surfpool")

def provision(rpc,payer,addresses):
    require_local(rpc)
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction,AccountMeta
    from solders.hash import Hash
    from solders.transaction import Transaction
    if not 8<=len(addresses)<=48 or len(set(addresses))!=len(addresses):
        raise ValueError("ALT requires 8-48 distinct addresses")
    program=Pubkey.from_string(ALT_PROGRAM)
    slot=call(rpc,"getSlot",[{"commitment":"processed"}])
    if type(slot)is not int:raise ValueError("invalid local slot")
    address,bump=Pubkey.find_program_address([bytes(payer.pubkey()),slot.to_bytes(8,"little")],program)
    keys=[AccountMeta(address,False,True),AccountMeta(payer.pubkey(),True,False),
          AccountMeta(payer.pubkey(),True,True),
          AccountMeta(Pubkey.from_string("11111111111111111111111111111111"),False,False)]
    create=(0).to_bytes(4,"little")+slot.to_bytes(8,"little")+bytes([bump])
    extensions=[]
    for offset in range(0,len(addresses),20):
        chunk=addresses[offset:offset+20]
        extension=(2).to_bytes(4,"little")+len(chunk).to_bytes(8,"little")
        extension+=b"".join(bytes(Pubkey.from_string(k)) for k in chunk)
        extensions.append(extension)
    for payload in (create,*extensions):
        bh=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
        tx=Transaction.new_signed_with_payer([Instruction(program,payload,keys)],payer.pubkey(),[payer],Hash.from_string(bh))
        if len(bytes(tx))>1232:raise ValueError("ALT setup packet too large")
        sig=call(rpc,"sendTransaction",[base64.b64encode(bytes(tx)).decode(),{"encoding":"base64","preflightCommitment":"processed"}])
        if not isinstance(sig,str):raise ValueError("local ALT setup rejected")
        for _ in range(40):
            status=call(rpc,"getSignatureStatuses",[[sig]])["value"][0]
            if status and status.get("err") is not None:raise ValueError("local ALT setup failed")
            if status and status.get("confirmationStatus") in ("processed","confirmed","finalized"):break
            time.sleep(.2)
        else:raise ValueError("local ALT setup unconfirmed")
    for _ in range(25):
        try:
            table=load_table(rpc,str(address))
            if len(table.addresses)==len(addresses):return table
        except ValueError:pass
        time.sleep(.2)
    raise ValueError("local ALT not visible")
