"""Offline-only integrity inventory for authenticated source-fork artifacts.

This does NOT reauthenticate upstream state or constitute signed execution proof.
A fixture missing its account/program evidence must not be labeled executable.
"""
import json
import os
from pathlib import Path
from arb.next_ten_atomic_routes import route_batch

DIRECTORIES={
    "first":"next-ten-dual-program-fixtures",
    "next":"following-ten-fixtures",
    "remaining":"remaining-24-fixtures",
}
def audit(root):
    root=Path(root)
    batches={}
    for batch,folder in DIRECTORIES.items():
        directory=root/folder
        records=[]
        for first,second in route_batch(batch):
            path=directory/(first+"__"+second+".json")
            item={"route":first+"__"+second,"fixture_present":path.is_file(),
                  "source_structure_present":False,"offline_execution_verified":False}
            if path.is_file():
                try:
                    content=json.loads(path.read_text())
                    item["source_structure_present"]=(
                        content.get("first_venue")==first and
                        content.get("second_venue")==second and
                        isinstance(content.get("accounts"),dict) and bool(content["accounts"]) and
                        isinstance(content.get("leg_evidence"),dict) and
                        first in content["leg_evidence"] and second in content["leg_evidence"] and
                        isinstance(content.get("route_mints"),list) and
                        len(content["route_mints"])==3)
                except (ValueError,TypeError,KeyError):
                    item["invalid_source_fixture"]=True
            records.append(item)
        batches[batch]={"target":len(records),"fixtures_present":sum(x["fixture_present"] for x in records),
                        "structurally_valid":sum(x["source_structure_present"] for x in records),
                        "routes":records}
    return {"status":"OFFLINE_SOURCE_ARTIFACT_AUDIT","broadcast":False,
            "upstream_rpc_reads":0,"source_reauthentication_performed":False,
            "signed_atomic_executions_verified":0,"batches":batches}

def main():
    report=audit(os.environ["SOURCE_FIXTURE_ROOT"])
    output=Path(os.environ["SOURCE_EVIDENCE_AUDIT_REPORT"])
    output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:{n:v for n,v in d.items() if n!="routes"}
                      for k,d in report["batches"].items()},indent=2))

if __name__=="__main__":
    main()
