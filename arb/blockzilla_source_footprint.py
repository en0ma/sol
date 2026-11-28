"""Unsigned, source-bound account-footprint research preflight.

Use the same existing venue instruction builders as isolated signing,
with deterministic placeholder user addresses and unit amounts. No keypair,
RPC, account mutation, transaction signature or live submission. A count
is not proof of runtime limits or acceptance. PumpSwap runtime-dependent
accounts remain unavailable in this preflight; do not guess their count.
"""
import hashlib
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.atomic_graph_coordinator import compile_route
from arb.source_snapshot_manifest import verify
from solders.pubkey import Pubkey

SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
# Research policy for the observed isolated fork, not a claim of a universal
# Solana maximum. Actual signed runtime results remain authoritative.
PREFERRED_KEYS=64

def instruction_footprint(instructions,payer):
    from solders.message import Message
    from solders.hash import Hash
    if not 2<=len(instructions)<=6 or not isinstance(payer,Pubkey):
        raise ValueError("invalid unsigned footprint instruction inventory")
    keys={payer}
    for ix in instructions:
        keys.add(ix.program_id)
        keys.update(meta.pubkey for meta in ix.accounts)
    message=Message.new_with_blockhash(instructions,payer,Hash.default())
    if set(message.account_keys)!=keys or len(message.account_keys)!=len(keys):
        raise ValueError("unsigned compiler and instruction key union disagree")
    return len(keys)

def source_footprint(fixture):
    verify(fixture)
    if any(fixture.get(k) is not False for k in SAFE):
        raise ValueError("unsafe source footprint fixture")
    rows=extract_pool_states(fixture)
    mints=fixture["route_mints"]
    proofs=fixture["leg_evidence_by_index"]
    base={"source_slot":fixture["state_accounts_observed_slot"],
          "manifest_sha256":fixture["state_account_manifest_sha256"],
          "preferred_key_budget":PREFERRED_KEYS,"resolved_account_key_estimate":None,
          "signed_packet_verified":False,"runtime_acceptance_verified":False,**SAFE}
    if len(rows)!=len(proofs) or not 3<=len(rows)<=6:
        raise ValueError("source footprint route identity mismatch")
    if any(r["venue"]=="pumpswap" for r in rows):
        return {**base,"status":"SOURCE_FOOTPRINT_RUNTIME_ACCOUNTS_UNAVAILABLE"}
    # Placeholder addresses have no private key material. Explicitly check
    # collisions with captured accounts and with every instruction key.
    existing=set(fixture["accounts"])
    domain=fixture["state_account_manifest_sha256"].encode("ascii")
    def placeholder(role):
        return str(Pubkey.from_bytes(hashlib.sha256(
            b"source-footprint-only-v1:"+domain+b":"+role.encode("ascii")).digest()))
    owner=placeholder("payer")
    users=[placeholder("token-"+str(i)) for i in range(len(mints))]
    synthetic={owner,*users}
    if len(synthetic)!=len(users)+1 or synthetic&existing:
        raise ValueError("source footprint placeholder collision")
    states={};evidence={};legs=[]
    from arb.next_ten_signed_atomic_offline import clmm_direction_evidence
    for i,(row,proof) in enumerate(zip(rows,proofs)):
        venue,pool=row["venue"],row["address"]
        if (proof.get("venue")!=venue or proof.get("pool")!=pool
                or not isinstance(proof.get("auxiliary"),dict)):
            raise ValueError("unsigned footprint source leg identity mismatch")
        key=(venue,pool)
        state=row["decoded_pool_state"]
        aux=dict(proof["auxiliary"])
        if venue=="raydium_clmm":
            aux.update(clmm_direction_evidence(state,mints[i],
                aux.get("tick_arrays_by_direction"),fixture["accounts"]))
        states[key]=state;evidence[key]=aux
        legs.append({"venue":venue,"pool":pool,"input_mint":mints[i],"output_mint":mints[i+1]})
    try:
        ixs=compile_route(legs,mints,states,evidence,owner,users,[1]*len(rows),[1]*len(rows))
        for i,ix in enumerate(ixs):
            ix_keys={str(meta.pubkey) for meta in ix.accounts}
            allowed={owner,users[i],users[i+1]}
            if (not allowed<=ix_keys or (ix_keys&synthetic)!=allowed
                    or str(ix.program_id) in synthetic):
                raise ValueError("unsigned footprint unexpected user account linkage")
        count=instruction_footprint(ixs,Pubkey.from_string(owner))
    except (ValueError,KeyError,TypeError,RuntimeError,OverflowError) as exc:
        return {**base,"status":"SOURCE_FOOTPRINT_BUILDER_UNAVAILABLE",
                "error_class":type(exc).__name__,"reason":str(exc)[:180]}
    return {**base,"status":"SOURCE_UNSIGNED_INSTRUCTION_KEY_UNION",
            "resolved_account_key_estimate":count,
            "within_preferred_key_budget":count<=PREFERRED_KEYS}

def select_six_hop_sources(rows,*,cap=2):
    """Prefer compiled footprints within the research budget, then unknown,
    then larger footprints. Preserve fallback candidates rather than treating
    a count as a verified runtime failure. Selection is before all signing.
    """
    if type(cap) is not int or not 1<=cap<=4:
        raise ValueError("invalid source footprint selection cap")
    if len(rows)>4 or len({r["id"] for r in rows})!=len(rows):
        raise ValueError("invalid six-hop source inventory")
    def rank(item):
        index,row=item
        evidence=row["source_account_footprint"]
        if any(evidence.get(k) is not False for k in SAFE):
            raise ValueError("unsafe source footprint selection")
        count=evidence.get("resolved_account_key_estimate")
        if count is None:
            return (1,0,index)
        if type(count) is not int or count<=0 or evidence.get("status")!="SOURCE_UNSIGNED_INSTRUCTION_KEY_UNION":
            raise ValueError("invalid unsigned key estimate")
        return (0,0,index) if count<=PREFERRED_KEYS else (2,count,index)
    return [r["id"] for _,r in sorted(enumerate(rows),key=rank)[:cap]]
