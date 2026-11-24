#!/usr/bin/env python3
"""Champion watch for tug_now3: poll workshop verdicts, publish the first
checkpoint that DOMINATES the model_0 baseline (5/5 wins + margin above the
baseline mean score_cm). Sponsor pre-authorized: "tug-чемпион".

Baseline (model_0, reference weights): 4/5 wins, mean score_cm ~3.55.
Criteria: 5/5 won AND mean score_cm > baseline * 1.5 (dominance, not luck).
Publish: tdesc/microduck-tug-of-war-<run_name> --no-private --enter. One shot.
"""
import json, glob, os, re, sys, time
from pathlib import Path

RUN_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else None
RUN_NAME = RUN_DIR.name.split("_", 2)[-1] if RUN_DIR else "tug_now3"
REPO_ID = f"tdesc/microduck-tug-of-war-{RUN_NAME}"
BASELINE_MEAN_CM = 3.55
POLL_S = 120

def read_verdicts(run_dir: Path):
    out = {}
    for j in sorted(glob.glob(str(run_dir / "workshop" / "model_*.json"))):
        n = re.search(r"model_(\d+)\.json$", j)
        if not n or int(n.group(1)) == 0:
            continue
        try:
            d = json.loads(Path(j).read_text())
            seeds = d.get("per_seed") or []
            wins = sum(1 for s in seeds if s.get("status") == "won")
            cms = [s.get("score_cm", 0) for s in seeds if s.get("status") == "won"]
            out[int(n.group(1))] = {
                "wins": wins,
                "seeds": len(seeds),
                "mean_cm": sum(cms) / len(cms) if cms else 0.0,
            }
        except (ValueError, KeyError):
            pass
    return out

def main():
    print(f"[champion] watching {RUN_DIR.name} | criteria: 5/5 wins + mean_cm > {BASELINE_MEAN_CM}*1.5 | publish: {REPO_ID}", flush=True)
    while True:
        verdicts = read_verdicts(RUN_DIR)
        for n, v in sorted(verdicts.items()):
            if v["wins"] == 5 and v["seeds"] == 5 and v["mean_cm"] > BASELINE_MEAN_CM * 1.5:
                print(f"[champion] FOUND: model_{n} — {v['wins']}/5 wins, mean_cm {v['mean_cm']:.2f} > {BASELINE_MEAN_CM * 1.5:.2f}", flush=True)
                cmd = (
                    f"cd /Users/valentin.kalinin/workspace/external/microduck-challenges && "
                    f"uv run publish --run {RUN_DIR} --checkpoint {n} "
                    f"--repo {REPO_ID} --no-private --enter"
                )
                r = os.system(cmd)
                print(f"[champion] publish exit: {r//256}", flush=True)
                return 0
        time.sleep(POLL_S)

if __name__ == "__main__":
    sys.exit(main())
