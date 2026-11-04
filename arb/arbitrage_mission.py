"""Repository-level mission guardrails for every arbitrage feature."""
from pathlib import Path
GOAL_PATH=Path(__file__).resolve().parents[1]/"docs"/"arbitrage-mission.md"
REQUIRED=("continuously discover","amount-aware","atomic","same-venue",
          "cross-venue","fail closed","no mainnet swap broadcasting")
def check():
    text=GOAL_PATH.read_text().lower()
    missing=[phrase for phrase in REQUIRED if phrase not in text]
    if missing:raise ValueError("Arbitrage mission missing required goals: "+", ".join(missing))
    return True
if __name__=="__main__":
    check()
    print("Arbitrage mission guardrails present")
