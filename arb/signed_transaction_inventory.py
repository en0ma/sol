"""Fail-closed, per-route signed Surfpool result export for CI.

Consumes existing source/offline artifacts; never infers paid fees or broadcasts.
"""
import argparse
import csv
import json
from pathlib import Path

COLUMNS = ("index", "venues", "legs", "source_status", "simulation_status",
           "profitability", "gross_delta_base_units", "net_delta_base_units",
           "compute_units", "reason", "source_fixture", "broadcast")


def collect(source, offline, ranking=None):
    if not isinstance(source, dict) or not isinstance(offline, dict):
        raise ValueError("both source and signed offline reports required")
    if offline.get("status") != "SIX_VENUE_SIGNED_OFFLINE_RESEARCH":
        raise ValueError("not a signed offline research report")
    if offline.get("broadcast") is not False or offline.get("actionable") is not False:
        raise ValueError("unsafe offline report")
    decisions = offline.get("route_decisions", {}).get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("signed decisions missing")
    if offline.get("signed_attempted") != len(decisions):
        raise ValueError("signed attempted count mismatch")
    routes = source.get("routes")
    if not isinstance(routes, list):
        raise ValueError("source route inventory missing")
    source_index = {}
    for r in routes:
        if not isinstance(r, dict) or type(r.get("index")) is not int:
            continue
        if r["index"] in source_index:
            raise ValueError("duplicate source route index")
        source_index[r["index"]] = r
    blocked = {}
    if ranking is not None:
        if not isinstance(ranking, dict) or not isinstance(ranking.get("all_results"), list):
            raise ValueError("source quote ranking invalid")
        for item in ranking["all_results"]:
            if not isinstance(item, dict) or type(item.get("index")) is not int:
                raise ValueError("invalid ranking item")
            idx = item["index"]
            if idx in blocked or idx not in source_index:
                raise ValueError("ranking/source indices inconsistent")
            blocked[idx] = item
        if set(blocked) != set(source_index):
            raise ValueError("ranking must account for all source candidates")
    seen = set()
    if ranking is not None:
        for i, item in blocked.items():
            r = source_index[i]
            if item.get("status") not in ("GROSS_INDICATIVE_ONLY", "QUOTE_BLOCKED"):
                raise ValueError("unsupported source quote evidence status")
            if item.get("status") == "GROSS_INDICATIVE_ONLY":
                delta = item.get("gross_delta_start_mint_base_units")
                if type(delta) is not int or item.get("positive_gross") is not (delta > 0):
                    raise ValueError("source gross ranking inconsistency")
    output = []
    for d in decisions:
        if not isinstance(d, dict) or type(d.get("index")) is not int:
            raise ValueError("invalid signed decision index")
        i = d["index"]
        if i in seen or i not in source_index:
            raise ValueError("duplicate or unbound signed route")
        seen.add(i)
        if d.get("broadcast") is not False or d.get("actionable") is not False:
            raise ValueError("unsafe signed decision")
        r = source_index[i]
        accepted = d.get("signed_execution_verified") is True
        gross = d.get("observed_gross_delta_start_mint_base_units")
        if gross is not None and type(gross) is not int:
            raise ValueError("noninteger signed gross")
        net_verified = d.get("net_profitability_verified") is True
        if net_verified:
            raise ValueError("independent net acceptance not implemented in this exporter")
        output.append({
            "index": i,
            "venues": ">".join(r.get("venues", [])) if isinstance(r.get("venues"), list)
                      else ">".join(str(l.get("venue", "?")) for l in r.get("legs", [])
                                    if isinstance(l, dict)),
            "legs": len(r["venues"]) if isinstance(r.get("venues"), list)
                    else len(r["legs"]) if isinstance(r.get("legs"), list) else None,
            "source_status": r.get("status"),
            "simulation_status": "SIGNED_ACCEPTED" if accepted else "SIGNED_REJECTED",
            "profitability": ("GROSS_LOSS_NET_NOT_VERIFIED" if accepted and gross is not None and gross < 0
                               else "GROSS_BREAK_EVEN_NET_NOT_VERIFIED" if accepted and gross == 0
                               else "UNKNOWN_COSTS" if accepted else "NOT_ESTABLISHED"),
            "gross_delta_base_units": gross if accepted else None,
            "net_delta_base_units": None,
            "compute_units": d.get("observed_compute_units") if accepted else None,
            "reason": ("observed signed gross loss; complete net fees not independently verified"
                       if gross is not None and gross < 0 else
                       "independent fee and net cost verification missing") if accepted
                      else "signed simulation not independently accepted",
            "source_fixture": r.get("fixture"),
            "broadcast": False,
        })
    for i, r in sorted(source_index.items()):
        if i in seen:
            continue
        venues = r.get("venues")
        legs = r.get("legs")
        output.append({
            "index": i,
            "venues": ">".join(venues) if isinstance(venues, list) else
                      ">".join(str(l.get("venue", "?")) for l in legs if isinstance(l, dict))
                      if isinstance(legs, list) else "",
            "legs": len(venues) if isinstance(venues, list) else
                    len(legs) if isinstance(legs, list) else None,
            "source_status": r.get("status"),
            "simulation_status": "NOT_ATTEMPTED",
            "profitability": "NOT_ESTABLISHED",
            "gross_delta_base_units": None,
            "net_delta_base_units": None,
            "compute_units": None,
            "reason": (blocked[i].get("reason", "source candidate not selected for signing")
                       if blocked.get(i, {}).get("status") == "QUOTE_BLOCKED"
                       else "source candidate not selected for signed offline simulation"),
            "source_fixture": r.get("fixture"),
            "broadcast": False,
        })
    output.sort(key=lambda row: row["index"])
    return {
        "status": "SIGNED_SIMULATION_TRANSACTION_INVENTORY",
        "observed_gross_loss_count": sum(r["profitability"] == "GROSS_LOSS_NET_NOT_VERIFIED" for r in output),
        "source_routes": len(routes),
        "signed_attempted": len(decisions),
        "signed_accepted": sum(r["simulation_status"] == "SIGNED_ACCEPTED" for r in output),
        "confirmed_profitable": 0,
        "confirmed_unprofitable": 0,
        "unknown_or_rejected": len(output),
        "rows": output,
        "actionable": False, "broadcast": False,
    }


def write(source_path, offline_path, output_dir):
    source = json.loads(Path(source_path).read_text())
    ranking_path = Path(source_path).parent / "six-venue-ranking.json"
    ranking = json.loads(ranking_path.read_text()) if ranking_path.is_file() else None
    offline = json.loads(Path(offline_path).read_text())
    result = collect(source, offline, ranking)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "transactions.json").write_text(json.dumps(result, indent=2) + "\n")
    with (target / "transactions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(result["rows"])
    lines = [
        "## Signed Surfpool transaction inventory",
        f"- Source candidates: {result['source_routes']}",
        f"- Signed attempts: {result['signed_attempted']}",
        f"- Independently signed accepted: {result['signed_accepted']}",
        "- Verified net profitable: **0 (not established)**",
        "- Verified net unprofitable: **0 (not established)**",
        "- Unknown / rejected / unattempted: " + str(result["unknown_or_rejected"]),
        "- Source quote blockers are shown per route when the ranking artifact exists.",
        "- Accepted gross-loss receipts are labelled as gross losses, never net-verified outcomes.",
        "",
        "Net P&L remains unknown until independent complete costs are audited. "
        "Gross signed SPL delta is not net profit. No mainnet broadcasts.",
        "",
        "| Route index | Venues | Simulation | Gross (raw start mint) | Profitability |",
        "|---|---|---|---:|---|",
    ]
    for row in result["rows"][:50]:
        lines.append("| {index} | {venues} | {simulation_status} | {gross_delta_base_units} | {profitability} |".format(**row))
    (target / "summary.md").write_text("\n".join(lines) + "\n")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--offline", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    report = write(args.source, args.offline, args.output_dir)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}))


if __name__ == "__main__":
    main()
