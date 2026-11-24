#!/usr/bin/env python3
"""Physiology guard for tug runs — the LEADING indicator the mean-collapse
watcher lacks (X-ray lesson, 2026-11-24: tug's obs_normalizer._var drifted 882%
from reference; the -390K collapses are the rope's float32-fragile physics
(D4: twist inertia 3e-8 kg·m²) hitting perception first, reward later).

Polls the run dir for NEW model_*.pt checkpoints (trainer saves every 25 iters).
For each, reads obs_normalizer._mean/_std/_var and the mlp weights, and tracks
growth between consecutive checkpoints:

  - var_ratio: ||var_k|| / ||var_{k-1}||   — perception chasing a wild input scale
  - wjump:     ||W_k - W_{k-1}||          — raw policy jump per 25 iters

Alerts (and optionally kills) when var_ratio explodes BEFORE the reward mean
follows it down. Default mode is alert-only: tonight it teaches us the healthy
run's var-growth signature; --kill arms the SIGTERM once thresholds are
calibrated against real data.

Usage: norm_watch.py <run_dir> <train_pid> [--warn 2.0] [--kill-at 5.0] [--kill]
"""
import argparse, glob, os, re, signal, sys, time, json
from pathlib import Path

import torch

POLL_S = 120


def load_norm(path: Path):
    d = torch.load(path, map_location="cpu", weights_only=False)
    sd = d.get("actor_state_dict") or d.get("model_state_dict")
    var = sum(v.float().norm().item() for k, v in sd.items() if k.endswith("obs_normalizer._var"))
    mean = sum(v.float().norm().item() for k, v in sd.items() if k.endswith("obs_normalizer._mean"))
    w = torch.cat([v.float().flatten() for k, v in sd.items() if k.startswith("mlp.")])
    return var, mean, w


def receipt(run_dir: Path, body: dict):
    body["schema"] = "colony.duck.norm_watch.v1"
    body["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(run_dir.parent / "norm_watch.jsonl", "a") as fh:
        fh.write(json.dumps(body) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("pid", type=int)
    ap.add_argument("--warn", type=float, default=2.0)
    ap.add_argument("--kill-at", type=float, default=5.0)
    ap.add_argument("--kill", action="store_true", help="arm SIGTERM (default: alert only)")
    a = ap.parse_args()
    run_dir = Path(a.run_dir)

    seen: dict[int, tuple[float, float, torch.Tensor]] = {}
    while True:
        for f in sorted(glob.glob(str(run_dir / "model_*.pt"))):
            n = int(re.search(r"model_(\d+)\.pt$", f).group(1))
            if n in seen or n == 0:
                continue
            try:
                var, mean, w = load_norm(Path(f))
            except Exception as e:  # half-written checkpoint mid-save
                print(f"[norm] model_{n}: unreadable ({e}), skip", flush=True)
                continue
            seen[n] = (var, mean, w)
            prev_n = max((k for k in seen if k < n), default=None)
            if prev_n is None:
                print(f"[norm] model_{n}: baseline var_norm={var:.3f} mean_norm={mean:.3f}", flush=True)
                continue
            pvar, _, pw = seen[prev_n]
            vr = var / pvar if pvar > 0 else 0.0
            wj = (w - pw).norm().item()
            line = f"[norm] model_{n}: var_ratio {vr:.2f}x vs model_{prev_n}, wjump {wj:.2f}"
            if vr >= a.kill_at and a.kill:
                print(line + " — KILL: perception physiology exploding", flush=True)
                try:
                    os.kill(a.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                receipt(run_dir, {"action": "kill", "checkpoint": n, "var_ratio": vr, "wjump": wj,
                                  "prev_checkpoint": prev_n})
                return 0
            if vr >= a.warn:
                print(line + " — WARN: perception chasing a wild input scale; blow-up risk rising", flush=True)
                receipt(run_dir, {"action": "warn", "checkpoint": n, "var_ratio": vr, "wjump": wj,
                                  "prev_checkpoint": prev_n})
            else:
                print(line, flush=True)
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
