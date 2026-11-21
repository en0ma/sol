"""Read-only authenticated pool-state registry and bounded incremental graph refresh.

This is state management, not a trading feed. Caller supplies decoded,
source-authenticated observations from a read-only RPC subscription. Slot
regressions, stale observations and ambiguous pool identity fail closed.
"""
from arb.authenticated_pool_graph import enumerate_cycles

class PoolStateRegistry:
    def __init__(self, *, max_slot_lag=20):
        if type(max_slot_lag) is not int or max_slot_lag<0:
            raise ValueError("invalid slot tolerance")
        self._records={}
        self._latest_slot=0
        self._max_slot_lag=max_slot_lag
        self._revision=0

    @property
    def revision(self):
        return self._revision

    def ingest(self,record):
        if not isinstance(record,dict) or record.get("authenticated") is not True:
            raise ValueError("unauthenticated pool update")
        venue=record.get("venue")
        address=record.get("pool",record.get("address"))
        mints=record.get("mints")
        slot=record.get("slot")
        if (not isinstance(venue,str) or not venue or not isinstance(address,str) or not address
                or not isinstance(mints,(list,tuple)) or len(mints)!=2
                or any(not isinstance(x,str) or not x for x in mints)
                or mints[0]==mints[1] or type(slot) is not int or slot<0):
            raise ValueError("invalid authenticated update identity")
        key=(venue,address)
        prior=self._records.get(key)
        if prior and slot<=prior["slot"]:
            raise ValueError("stale or duplicate pool slot")
        if slot+self._max_slot_lag<self._latest_slot:
            raise ValueError("out-of-window pool observation")
        item=dict(record,pool=address,mints=list(mints))
        self._records[key]=item
        self._latest_slot=max(self._latest_slot,slot)
        self._revision+=1
        return {"revision":self._revision,"pool_identity":key,
                "slot":slot,"broadcast":False}

    def invalidate(self,venue,address,slot):
        key=(venue,address)
        old=self._records.get(key)
        if old is None:
            return False
        if type(slot) is not int or slot<old["slot"]:
            raise ValueError("stale invalidation slot")
        del self._records[key]
        self._revision+=1
        return True

    def snapshot(self):
        fresh=[dict(record) for record in self._records.values()
               if record["slot"]+self._max_slot_lag>=self._latest_slot]
        return sorted(fresh,key=lambda r:(r["venue"],r["pool"]))

    def routes(self,*,start_mints=None,min_legs=2,max_legs=6,max_results=10000):
        result=enumerate_cycles(self.snapshot(),start_mints=start_mints,
                                min_legs=min_legs,max_legs=max_legs,
                                max_results=max_results)
        return {"registry_revision":self._revision,"observed_slot":self._latest_slot,
                "candidates":result,"candidate_count":len(result),
                "actionable":False,"live_execution_approved":False,"broadcast":False}
