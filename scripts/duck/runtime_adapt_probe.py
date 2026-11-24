#!/usr/bin/env python3
"""Runtime-only adaptation probe: how much of the gentle adaptation step lives
in PERCEPTION (obs_normalizer stats) rather than motor weights?

Four variants of the same banked tug peak, all judged by the Arena's 5-seed
scorer (prereg runtime_perception_probe, sha 494136e0):

  born          gen1 model_50 as-is                    (motor + birth perception)
  frozen_birth  gen1 model_50 + reference obsnorm      (perception frozen at birth:
                                                        the "universal knowledge" extreme)
  runtime_recal gen1 model_50 + live obsnorm from the running
                gentle resume (tug_ws1 model_<latest>)  (motor frozen, perception
                                                        re-learned from live pulling)
  gentle_step   tug_ws1 model_<latest> as-is           (motor + perception both moved:
                                                        the full gentle step, ceiling)

Usage: runtime_adapt_probe.py [--weights PATH] [--donor PATH] [--ref PATH] [--skip born]
Verdict lines compare against prereg P1 (runtime_recal >= 80% of gentle_step
mean_cm) and P2 (frozen_birth < born on mean_cm).
"""
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
PROBE = Path("/tmp/runtime_probe")
EVENT = "tug-of-war"


def donor_normalizer(path: Path) -> dict:
    d = torch.load(path, map_location="cpu", weights_only=False)
    sd = d.get("actor_state_dict") or d.get("model_state_dict")
    return {k: v.clone() for k, v in sd.items() if k.startswith("obs_normalizer.")}


def surgery(base: Path, norm: dict, out: Path):
    d = torch.load(base, map_location="cpu", weights_only=False)
    key = "actor_state_dict" if "actor_state_dict" in d else "model_state_dict"
    sd = d[key]
    swapped = 0
    for k in list(sd.keys()):
        if k.startswith("obs_normalizer.") and k in norm:
            sd[k] = norm[k]
            swapped += 1
    d[key] = sd
    torch.save(d, out)
    return swapped


def score(checkpoint: Path, tag: str) -> dict:
    """Export one checkpoint to ONNX and let the Arena judge 5 seeds.
    publish's dry-run always writes publish-eval/policy.onnx — score it before
    the next variant's export overwrites it."""
    base = ["uv", "run", "publish", "--checkpoint-file", str(checkpoint),
            "--repo", "local/microduck-eval", "--dry-run", "--allow-dirty"]
    pub = subprocess.run(base, cwd=REPO, capture_output=True, text=True)
    if (REPO / "publish-eval/policy.onnx").exists() is False or pub.returncode != 0:
        pub = subprocess.run(base + ["--task", "Mjlab-TugOfWar-MicroDuck"],
                             cwd=REPO, capture_output=True, text=True)
    onnx_path = REPO / "publish-eval/policy.onnx"
    if not onnx_path.exists():
        return {"tag": tag, "raw": f"export failed: {(pub.stderr or pub.stdout)[-200:]}"}
    r = subprocess.run(
        ["uv", "run", "--group", "workshop", "arena", "score", str(onnx_path), "--event", EVENT],
        cwd=REPO, capture_output=True, text=True)
    text = r.stdout + r.stderr
    # arena's rating ledger: "seed N: <side> <status> <+/-X.X> cm at T s" … "rating: S cm"
    seeds = re.findall(r"seed (\d+): \w+ (\w+)\s+(-?[\d.]+) cm", text)
    rating = re.search(r"rating:\s*(-?[\d.]+)\s*cm", text)
    wins = sum(1 for _, st, _ in seeds if st in ("won", "pit_won"))
    verdict = {"tag": tag, "seeds": [{"seed": int(n), "status": st, "cm": float(c)} for n, st, c in seeds],
               "wins": wins, "seed_count": len(seeds), "raw": " ".join(text.split())[:200]}
    if rating:
        verdict["mean_cm"] = float(rating.group(1))
    return verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="logs/rsl_rl/tug_of_war/2026-11-24_14-09-31_tug_gentle1/model_50.pt")
    ap.add_argument("--donor", default="logs/rsl_rl/tug_of_war/2026-11-24_20-30-39_tug_ws1")
    ap.add_argument("--ref", default="logs/rsl_rl/sprint_2m/warmstart_ref/model_ref.pt")
    ap.add_argument("--skip", default="")
    a = ap.parse_args()

    weights = REPO / a.weights
    donor_dir = REPO / a.donor
    donor_ck = sorted(donor_dir.glob("model_*.pt"), key=lambda p: int(re.search(r"model_(\d+)", p.name).group(1)))[-1]
    ref = REPO / a.ref
    PROBE.mkdir(exist_ok=True)

    live_norm = donor_normalizer(donor_ck)
    ref_norm = donor_normalizer(ref)

    variants = {}
    if "born" not in a.skip:
        variants["born"] = weights
    if "frozen_birth" not in a.skip:
        p = PROBE / "frozen_birth_model_0.pt"
        print(f"[surgery] frozen_birth: swap {surgery(weights, ref_norm, p)} obsnorm tensors <- {ref.name}")
        variants["frozen_birth"] = p
    if "runtime_recal" not in a.skip:
        p = PROBE / "runtime_recal_model_0.pt"
        print(f"[surgery] runtime_recal: swap {surgery(weights, live_norm, p)} obsnorm tensors <- {donor_ck.name}")
        variants["runtime_recal"] = p
    if "gentle_step" not in a.skip:
        variants["gentle_step"] = donor_ck

    results = []
    for tag, ck in variants.items():
        print(f"[score] {tag} <- {ck}", flush=True)
        v = score(ck, tag)
        results.append(v)
        print(f"[score] {tag}: rating={v.get('mean_cm')} cm · {v.get('wins')}/{v.get('seed_count')} wins", flush=True)

    (PROBE / "probe_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    by = {v["tag"]: v for v in results}
    g = by.get("gentle_step", {}).get("mean_cm")
    r3 = by.get("runtime_recal", {}).get("mean_cm")
    b = by.get("born", {}).get("mean_cm")
    fb = by.get("frozen_birth", {}).get("mean_cm")
    print("\n=== verdict vs prereg 494136e0 ===")
    if g is not None and r3 is not None and g != 0:
        share = r3 / g * 100
        print(f"P1 runtime_recal {r3:.2f} of gentle_step {g:.2f} cm = {share:.0f}% (need >=80%: {'PASS' if share >= 80 else 'FAIL'})")
    if b is not None and fb is not None:
        print(f"P2 frozen_birth {fb:.2f} < born {b:.2f} cm ({'PASS' if fb < b else 'FAIL'})")


if __name__ == "__main__":
    sys.exit(main())
