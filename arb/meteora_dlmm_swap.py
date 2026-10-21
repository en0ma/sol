"""Meteora DLMM legacy exact-input swap instruction, construction only.

IDL: MeteoraAg/dlmm-sdk idls/dlmm.json, instruction "swap".
Caller MUST independently authenticate pool, oracle, mint/vault accounts and
the ordered bin-array path. No quotes, RPC writes, live approval or broadcast.
"""
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from arb.meteora_dlmm import PROGRAM
from arb.token_vaults import TOKEN_PROGRAM
from arb.meteora_dlmm_bin_preflight import bin_array_pda

SWAP_DISCRIMINATOR=bytes([248,198,158,145,225,117,135,200])
EVENT_AUTHORITY_SEED=b"__event_authority"

def build_swap(pool,state,authority,user_input,user_output,oracle,
               bin_arrays,amount_in,min_amount_out,*,input_is_x,
               bitmap_extension=None):
    if type(input_is_x) is not bool:
        raise ValueError("DLMM direction must be explicit boolean")
    if any(type(v) is not int or not 0<v<1<<64 for v in (amount_in,min_amount_out)):
        raise ValueError("DLMM exact-input amount and nonzero threshold required")
    if state.get("status")!=0 or state.get("token_mint_x_program_flag")!=0 or state.get("token_mint_y_program_flag")!=0:
        raise ValueError("DLMM pool disabled or nonclassic token mint")
    if len({state["token_x_mint"],state["token_y_mint"],state["reserve_x"],state["reserve_y"]})!=4:
        raise ValueError("DLMM pool mint or reserve duplicates")
    if not isinstance(bin_arrays,(tuple,list)) or not 1<=len(bin_arrays)<=3:
        raise ValueError("one to three authenticated DLMM bin arrays required")
    if len(set(bin_arrays))!=len(bin_arrays):
        raise ValueError("DLMM bin array reuse")
    p=Pubkey.from_string(PROGRAM)
    keys=[pool, bitmap_extension or PROGRAM, state["reserve_x"],state["reserve_y"],
          user_input,user_output,state["token_x_mint"],state["token_y_mint"],
          oracle,PROGRAM,authority,TOKEN_PROGRAM,TOKEN_PROGRAM,
          str(Pubkey.find_program_address([EVENT_AUTHORITY_SEED],p)[0]),PROGRAM]
    if any(not isinstance(x,str) for x in keys):
        raise ValueError("missing DLMM account")
    # Optional accounts use the program ID as a readonly placeholder (Anchor).
    writable={0,2,3,4,5,8}
    if bitmap_extension is not None:
        writable.add(1)
    metas=[AccountMeta(Pubkey.from_string(key),i==10,i in writable)
           for i,key in enumerate(keys)]
    active_index=state.get("active_bin_array_index")
    if type(active_index) is not int:
        raise ValueError("authenticated DLMM active bin index required")
    allowed={bin_array_pda(pool,active_index+i) for i in (-1,0,1)}
    if bin_array_pda(pool,active_index) not in bin_arrays or any(x not in allowed for x in bin_arrays):
        raise ValueError("bin array path not within authenticated active neighborhood")
    metas.extend(AccountMeta(Pubkey.from_string(x),False,True) for x in bin_arrays)
    data=SWAP_DISCRIMINATOR+amount_in.to_bytes(8,"little")+min_amount_out.to_bytes(8,"little")
    return Instruction(p,data,metas)
