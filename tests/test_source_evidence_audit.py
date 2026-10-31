import json
import tempfile
import unittest
from pathlib import Path
from arb.source_evidence_audit import audit
from arb.next_ten_atomic_routes import route_batch

class SourceEvidenceAuditTests(unittest.TestCase):
    def test_missing_fixtures_never_count_as_execution(self):
        with tempfile.TemporaryDirectory() as d:
            report=audit(d)
        self.assertEqual(report["signed_atomic_executions_verified"],0)
        self.assertEqual(report["upstream_rpc_reads"],0)
        self.assertEqual([report["batches"][x]["target"] for x in ("first","next","remaining")],[10,10,24])
    def test_structural_fixture_is_not_execution_proof(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"next-ten-dual-program-fixtures"
            root.mkdir()
            a,b=route_batch("first")[0]
            (root/(a+"__"+b+".json")).write_text(json.dumps({
                "first_venue":a,"second_venue":b,"accounts":{"a":{"owner":"owner"}},
                "leg_evidence":{a:{},b:{}},"route_mints":["a","b","a"]}))
            result=audit(d)
        self.assertEqual(result["batches"]["first"]["structurally_valid"],1)
        self.assertEqual(result["signed_atomic_executions_verified"],0)

if __name__=="__main__":unittest.main()
