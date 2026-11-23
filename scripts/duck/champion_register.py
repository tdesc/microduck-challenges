#!/usr/bin/env python3
"""DuckCortex artifact 2/3: champion register per discipline.

Reads (a) workshop/*.json verdicts (the inline demon's judgments — durable data)
and (b) the outcome-receipt chain (publication receipts), and prints/writes the
champion register: per discipline, the best checkpoint + why + publication ref.

Usage:
  champion_register.py --event sock-heist-6m --run-dir logs/rsl_rl/sock_heist_6m/<run> [--out duck_champions.json]
  champion_register.py --all          # every discipline with runs in logs/rsl_rl/
"""
import argparse, json, glob, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTER = REPO / "duck_receipts" / "duck_champions.json"


def workshop_verdicts(run_dir: Path):
    out = {}
    for j in sorted(glob.glob(str(run_dir / "workshop" / "model_*.json"))):
        n = re.search(r"model_(\d+)\.json$", j)
        if not n:
            continue
        try:
            d = json.loads(Path(j).read_text())
            if d.get("score") is not None and d.get("seeds_finished", 0) >= 5:
                out[int(n.group(1))] = d
        except ValueError:
            pass
    return out


def best_from_verdicts(verdicts):
    finished = {k: v for k, v in verdicts.items() if v.get("seeds_finished", 0) >= 5 and isinstance(v.get("score"), (int, float))}
    if not finished:
        return None
    n = min(finished, key=lambda k: finished[k]["score"])
    return {"checkpoint": n, "score": finished[n]["score"], "seeds_finished": finished[n].get("seeds_finished", 5), "source": "workshop"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event")
    ap.add_argument("--run-dir")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    register = json.loads(REGISTER.read_text()) if REGISTER.exists() else {}
    pairs = []
    if args.all:
        for task_dir in sorted((REPO / "logs" / "rsl_rl").glob("*")):
            for run in sorted(task_dir.glob("*")):
                pairs.append((task_dir.name, run))
    else:
        pairs.append((args.event, Path(args.run_dir)))

    for event, run in pairs:
        verdicts = workshop_verdicts(Path(run))
        best = best_from_verdicts(verdicts)
        if not best:
            print(f"{event}: no 5/5 verdicts in {run.name}")
            continue
        champ = {
            "event": event,
            "run": run.name,
            **best,
            "registered_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        }
        old = register.get(event)
        improved = old is None or (best["score"] or 99) < (old.get("score") or 99)
        mark = "NEW CHAMPION" if improved else "(current champion better)"
        print(f"{event}: best {best['score']}s @ model_{best['checkpoint']} ({run.name}) — {mark}")
        if improved:
            register[event] = champ

    if args.out:
        Path(args.out).write_text(json.dumps(register, ensure_ascii=False, indent=2) + "\n")
        print("register written:", args.out)
    else:
        REGISTER.parent.mkdir(parents=True, exist_ok=True)
        REGISTER.write_text(json.dumps(register, ensure_ascii=False, indent=2) + "\n")
        print("register updated:", REGISTER)


if __name__ == "__main__":
    main()
