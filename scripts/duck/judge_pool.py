#!/usr/bin/env python3
"""Parallel checkpoint judge (workflow findings: ~3x serial judge pool + 5-10x
'morning cycle' — read workshop/*.json first, score only what is missing).

Usage: judge_pool.py <run_dir> <event> [workers=3] [--step N]
Reads logs/<discipline>/<run>/workshop/model_N.json as already-judged verdicts
(the workshop demon writes them 1-3 min after each checkpoint), then export+score
only the unjudged checkpoints with `workers` parallel processes.
"""
import concurrent.futures, json, glob, os, re, subprocess, sys
from pathlib import Path

def judged_scores(run_dir: Path):
    out = {}
    for j in sorted(glob.glob(str(run_dir / "workshop" / "model_*.json"))):
        n = re.search(r"model_(\d+)\.json$", j)
        if not n:
            continue
        try:
            d = json.loads(Path(j).read_text())
            out[int(n.group(1))] = {"score": d.get("score"), "finished": d.get("seeds_finished")}
        except ValueError:
            pass
    return out

def export_and_score(run_dir: Path, event: str, n: int) -> str:
    cmd = (
        f"uv run publish --run {run_dir} --checkpoint {n} --repo local/microduck-eval "
        f"--dry-run --allow-dirty >/dev/null 2>&1 && "
        f"uv run --group workshop arena score publish-eval/policy.onnx --event {event}"
    )
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    m = re.findall(r"(scored at [\d.]+ m/s|score [\d.]+s? ?· \d/\d(?: finished)?)", r.stdout)
    return f"checkpoint {n}: " + " · ".join(m) if m else f"checkpoint {n}: no parseable score"

def main():
    if len(sys.argv) < 3:
        print("usage: judge_pool.py <run_dir> <event> [workers=3]"); sys.exit(3)
    run_dir, event = Path(sys.argv[1]), sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    done = judged_scores(run_dir)
    all_ck = sorted(
        int(re.search(r"model_(\d+)\.pt$", p).group(1))
        for p in glob.glob(str(run_dir / "model_*.pt"))
    )
    todo = [n for n in all_ck if n not in done]
    print(f"judge_pool: {len(done)} already judged (workshop), {len(todo)} to score: {todo}")
    if not todo:
        for n in all_ck:
            print(f"checkpoint {n}: score {done[n]['score']} · {done[n]['finished']}/5 finished (workshop)")
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(export_and_score, run_dir, event, n) for n in todo]
        for f in concurrent.futures.as_completed(futs):
            print(f.result(), flush=True)

if __name__ == "__main__":
    main()
