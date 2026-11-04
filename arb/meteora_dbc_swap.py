"""Original Meteora DBC Anchor swap instruction builder (offline-only primitive).

Account order and discriminator match the published original DBC IDL.
This does NOT represent a verified signed swap or permit mainnet broadcast.
Token-2022 extensions and transfer hooks are intentionally not supported
by this initial original SPL-only instruction path.
"""
from solders.pubkey import Pubkey
from solders.instruction import Instruction,AccountMeta
from arb.meteora_dbc_seventh_venue_source import PROGRAM, POOL_AUTHORITY
from arb.meteora_dbc_seventh_state_capture import TOKEN_PROGRAM

DISC=bytes([248,198,158,145,225,117,135,200])
PROGRAM_KEY=Pubkey.from_string(PROGRAM)
AUTHORITY=Pubkey.from_string(POOL_AUTHORITY)


def build_swap(pool, fields, signer, user_source, user_destination,
               amount_in, minimum_out, *, swap_base_for_quote):
    if (type(amount_in) is not int or type(minimum_out) is not int
            or not 0<amount_in<1<<64 or not 0<minimum_out<1<<64
            or type(swap_base_for_quote) is not bool):
        raise ValueError("DBC nonzero bounded exact-in swap intent required")
    if (not isinstance(fields,dict)
            or fields.get("pool_type")!=0
            or fields.get("is_migrated")!=0
            or fields.get("migration_progress")!=0
            or fields.get("base_token_program")!=TOKEN_PROGRAM
            or fields.get("quote_token_program")!=TOKEN_PROGRAM):
        raise ValueError("DBC original legacy SPL un-migrated source required")
    for required in ("config","base_mint","quote_mint","base_vault","quote_vault"):
        if not isinstance(fields.get(required),str):
            raise ValueError("DBC original source field missing: "+required)
    if fields["base_mint"]==fields["quote_mint"]:
        raise ValueError("DBC original base/quote identity collision")
    # SDK original Anchor swap instruction account order.
    event_authority,_=Pubkey.find_program_address([b"__event_authority"],PROGRAM_KEY)
    def key(s):return Pubkey.from_string(s)
    def meta(pub,writable=False,signer=False):
        return AccountMeta(pub,signer,writable)
    keys=[
      meta(AUTHORITY),
      meta(key(fields["config"])),
      meta(key(pool),True),
      meta(key(user_source),True),
      meta(key(user_destination),True),
      meta(key(fields["base_vault"]),True),
      meta(key(fields["quote_vault"]),True),
      meta(key(fields["base_mint"])),
      meta(key(fields["quote_mint"])),
      meta(key(signer),True,True),
      meta(key(TOKEN_PROGRAM)),
      meta(key(TOKEN_PROGRAM)),
      # Anchor optional referral account absent, represented by program ID.
      meta(PROGRAM_KEY),
      meta(event_authority),
      meta(PROGRAM_KEY),
    ]
    if len({str(x.pubkey) for x in keys[:10]})!=10:
        raise ValueError("DBC source/user signer account role collision")
    direction=(fields["base_mint"],fields["quote_mint"]) if swap_base_for_quote else (
               fields["quote_mint"],fields["base_mint"])
    data=DISC+amount_in.to_bytes(8,"little")+minimum_out.to_bytes(8,"little")
    return Instruction(PROGRAM_KEY,data,keys),{"direction":direction,
        "amount_in":amount_in,"minimum_out":minimum_out,
        "offline_only":True,"signed_execution_verified":False,
        "registry_admission_approved":False}
