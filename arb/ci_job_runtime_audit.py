"""Zero-upstream-RPC retrospective audit of GitHub Actions job timings.

Never disables gates automatically. Recommends reviewing long/obsolete jobs.
"""
import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

REQUIRED={"pairwise-capability-audit","surfpool-smoke-test",
          "authenticated-source-fork","source-evidence-audit",
          "isolated-orca-execution"}
OPTIONAL_PATTERNS=("three-hop","standalone","legacy","historical")
def seconds(start,end):
    if not start or not end:return None
    try:
        return round((datetime.fromisoformat(end.replace("Z","+00:00"))-
                      datetime.fromisoformat(start.replace("Z","+00:00"))).total_seconds())
    except ValueError:
        return None

def audit(jobs,*,warn_seconds=600):
    entries=[]
    recommendations=[]
    for job in jobs:
        name=job.get("name","")
        if not name:continue
        duration=seconds(job.get("started_at"),job.get("completed_at"))
        slow_steps=[]
        for step in job.get("steps") or []:
            elapsed=seconds(step.get("started_at"),step.get("completed_at"))
            if elapsed is not None and elapsed>=120:
                slow_steps.append({"name":step.get("name"),"duration_seconds":elapsed})
        entries.append({"name":name,"conclusion":job.get("conclusion"),
                        "duration_seconds":duration,"slow_steps":slow_steps})
        if duration is not None and duration>=warn_seconds:
            recommendations.append({"job":name,"reason":"LONG_RUNTIME","seconds":duration,
                                    "action":"Review repeated work, artifacts and upstream reads"})
        if any(pattern in name.lower() for pattern in OPTIONAL_PATTERNS):
            recommendations.append({"job":name,"reason":"HISTORICAL_OR_OPTIONAL_WORK",
                                    "action":"Confirm this job is manual-only"})
    missing=sorted(REQUIRED-{x["name"] for x in entries})
    if missing:
        recommendations.append({"reason":"REQUIRED_JOB_NOT_IN_RUN",
                                "jobs":missing,"action":"Confirm skipped or renamed gates"})
    return {"status":"CI_JOB_RUNTIME_AUDIT","upstream_rpc_calls":0,
            "source":"PREVIOUS_COMPLETED_GITHUB_ACTIONS_RUN",
            "jobs":entries,"recommendations":recommendations,
            "no_automatic_job_disabling":True}

def request_json(url,token):
    req=urllib.request.Request(url,headers={
        "Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
        "User-Agent":"sol-ci-job-runtime-auditor"})
    with urllib.request.urlopen(req,timeout=15) as response:
        return json.load(response)

def main():
    repo=os.environ["GITHUB_REPOSITORY"]
    token=os.environ["GH_TOKEN"]
    workflow=os.environ.get("GITHUB_WORKFLOW","Surfpool CI")
    run_id=int(os.environ["GITHUB_RUN_ID"])
    url=f"https://api.github.com/repos/{repo}/actions/runs"
    data=request_json(url+"?per_page=20",token)
    prior=next((x for x in data.get("workflow_runs",[])
                if x.get("name")==workflow and x.get("id")!=run_id
                and x.get("status")=="completed"),None)
    if prior is None:
        report={"status":"NO_COMPLETED_PRIOR_RUN","upstream_rpc_calls":0,
                "jobs":[],"recommendations":[]}
    else:
        jobs=[]
        for page in range(1,6):
            result=request_json(url+"/"+str(prior["id"])+f"/jobs?per_page=100&page={page}",token)
            jobs.extend(result.get("jobs",[]))
            if len(result.get("jobs",[]))<100:break
        report=audit(jobs)
        report["audited_run_id"]=prior["id"]
        report["audited_run_url"]=prior.get("html_url")
    Path(os.environ["CI_RUNTIME_AUDIT_OUTPUT"]).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "audited_run_id":report.get("audited_run_id"),
                      "recommendation_count":len(report["recommendations"])}))

if __name__=="__main__":main()
