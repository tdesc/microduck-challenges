#!/usr/bin/env python3
"""Duck outcome receipts — append-only hash-chain of training-run outcomes.

DuckCortex minimal write-path, artifact 1/3 (advisor verdict 2026-11-23).
Each receipt: {schema, ts, run, task, checkpoint, status, score, seeds_finished,
hypothesis_ref, note, prev_hash, digest}. prev_hash links to the previous
receipt's digest — tampering with any entry breaks the chain (verify_chain).

Usage:
  outcome_receipt.py append --run <run_dir> --task <event> --checkpoint N \
      --status finished|kill|timeout|fall --score S --seeds 5 [--hypothesis-ref <sha>] [--note "..."]
  outcome_receipt.py verify
  outcome_receipt.py best --task <event>     # best receipt per champion-register
Store: duck_receipts/outcome_chain.jsonl (committed to git — the receipts ARE
the duck's durable memory between runs).
"""
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "duck_receipts" / "outcome_chain.jsonl"
SCHEMA = "colony.duck.outcome_receipt.v1"


def canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(receipt_without_digest: dict) -> str:
    return hashlib.sha256(canonical(receipt_without_digest)).hexdigest()


def load_chain():
    if not STORE.exists():
        return []
    return [json.loads(line) for line in STORE.read_text().splitlines() if line.strip()]


def cmd_append(args):
    chain = load_chain()
    prev = chain[-1]["digest"] if chain else "GENESIS"
    receipt = {
        "schema": SCHEMA,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run": args.run,
        "task": args.task,
        "checkpoint": args.checkpoint,
        "status": args.status,
        "score": args.score,
        "seeds_finished": args.seeds,
        "hypothesis_ref": args.hypothesis_ref or "",
        "note": args.note or "",
        "prev_hash": prev,
    }
    receipt["digest"] = digest(receipt)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with STORE.open("a") as fh:
        fh.write(json.dumps(receipt, ensure_ascii=False) + "\n")
    print(f"receipt appended: {receipt['digest'][:16]} prev={prev[:16]}")
    return 0


def cmd_verify(args=None):
    chain = load_chain()
    prev = "GENESIS"
    for i, r in enumerate(chain):
        body = {k: v for k, v in r.items() if k != "digest"}
        if r.get("prev_hash") != prev:
            print(f"CHAIN BROKEN at entry {i}: prev_hash mismatch")
            return 42
        if digest(body) != r.get("digest"):
            print(f"CHAIN BROKEN at entry {i}: digest mismatch (entry edited)")
            return 42
        prev = r["digest"]
    print(f"chain OK: {len(chain)} receipts, head={prev[:16]}")
    return 0


def cmd_best(args):
    best = None
    for r in load_chain():
        if r["task"] != args.task or r["status"] != "finished" or r["score"] is None:
            continue
        if args.min_seeds and (r["seeds_finished"] or 0) < args.min_seeds:
            continue
        if best is None or r["score"] < best["score"]:
            best = r
    if best is None:
        print(f"no finished receipt for {args.task}")
        return 1
    print("champion:", json.dumps(best, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append")
    a.add_argument("--run", required=True)
    a.add_argument("--task", required=True)
    a.add_argument("--checkpoint", type=int, required=True)
    a.add_argument("--status", required=True, choices=("finished", "kill", "timeout", "fall"))
    a.add_argument("--score", type=float, default=None)
    a.add_argument("--seeds", type=int, default=0)
    a.add_argument("--hypothesis-ref", default="")
    a.add_argument("--note", default="")
    v = sub.add_parser("verify")
    b = sub.add_parser("best")
    b.add_argument("--task", required=True)
    b.add_argument("--min-seeds", type=int, default=5)
    args = ap.parse_args()
    return {"append": cmd_append, "verify": cmd_verify, "best": cmd_best}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
