#!/usr/bin/env python3
"""DuckCortex artifact 3/3: prereg-freeze — a falsifiable prediction frozen
BEFORE a training run, with sha256 commitment (the cohort_commitment pattern).

The night (or the sponsor) states: hypothesis, the falsifiable prediction
(numbers), and the run parameters. The freeze file (prereg/<ts>-<name>.json +
its sha256 sidecar) is immutable-by-convention: the morning judge reads it and
rules PREDICTION_FULFILLED / PREDICTION_REFUTED / NOT_EVALUABLE.

Usage:
  prereg.py freeze --name tug_night1 --hypothesis "256 envs cover the 250-500 peak window" \
      --prediction "best checkpoint <= 60s; opponent_in_pit >= 0.15 by iter 400" \
      --refutes "score > 60s at any checkpoint, or opponent_in_pit < 0.05 at 400" \
      --run-task Mjlab-TugOfWar-MicroDuck --run-envs 256 --run-iters 400 --run-seed 2
  prereg.py judge --file prereg/<file>.json --verdict PREDICTION_FULFILLED --evidence "workshop jsons"
"""
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PREREG = REPO / "duck_receipts" / "prereg"


def canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def cmd_freeze(a):
    ts = datetime.now(timezone.utc)
    doc = {
        "schema": "colony.duck.prereg.v1",
        "frozen_at": ts.isoformat(timespec="seconds"),
        "name": a.name,
        "hypothesis": a.hypothesis,
        "prediction": a.prediction,
        "refutes": a.refutes,
        "run": {"task": a.run_task, "num_envs": a.run_envs, "max_iterations": a.run_iters, "seed": a.run_seed},
    }
    sha = hashlib.sha256(canonical(doc)).hexdigest()
    doc["commitment_sha256"] = sha
    PREREG.mkdir(parents=True, exist_ok=True)
    f = PREREG / f"{ts.strftime('%Y%m%d_%H%M%S')}-{a.name}.json"
    f.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    (f.with_suffix(".sha256")).write_text(sha + "\n")
    print(f"prereg frozen: {f} | commitment sha256={sha[:16]}…")
    return 0


def cmd_judge(a):
    f = Path(a.file)
    d = json.loads(f.read_text())
    # честность: вердикт обязан ссылаться на замороженный sha
    sha = hashlib.sha256(canonical({k: v for k, v in d.items() if k not in ("verdict", "commitment_sha256")})).hexdigest()
    ok = sha == d.get("commitment_sha256")
    d["verdict"] = {"ruling": a.verdict, "evidence": a.evidence, "commitment_intact": ok}
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n")
    print(f"judged: {a.verdict} | commitment_intact={ok}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    fr = sub.add_parser("freeze")
    fr.add_argument("--name", required=True)
    fr.add_argument("--hypothesis", required=True)
    fr.add_argument("--prediction", required=True)
    fr.add_argument("--refutes", required=True)
    fr.add_argument("--run-task", default="")
    fr.add_argument("--run-envs", type=int, default=0)
    fr.add_argument("--run-iters", type=int, default=0)
    fr.add_argument("--run-seed", type=int, default=0)
    j = sub.add_parser("judge")
    j.add_argument("--file", required=True)
    j.add_argument("--verdict", required=True, choices=("PREDICTION_FULFILLED", "PREDICTION_REFUTED", "NOT_EVALUABLE"))
    j.add_argument("--evidence", default="")
    args = ap.parse_args()
    return {"freeze": cmd_freeze, "judge": cmd_judge}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
