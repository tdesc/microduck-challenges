#!/usr/bin/env python3
"""Early degeneration detector ("statue kill") — from the 2026-11-23 workflow findings.

Rule (verified on upright3=statue vs m1night1=healthy, workflow confirmers):
  kill when, at iteration >= 250:
    error_vel_xy(250) >= 1.8 * error_vel_xy(100)   (velocity error GROWING)
    and Episode_Reward/track_linear_velocity(250) < 0.02  (flat tracking)

Exit codes: 0 healthy/enough data, 42 DEGENERATE (kill the run), 1 not enough data yet, 3 usage.
"""
import glob, sys
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

def at(ea, tag, step):
    if tag not in ea.Tags()["scalars"]:
        return None
    for e in ea.Scalars(tag):
        if e.step >= step:
            return e.value
    return None

def main(run_dir: str, kill_step: int = 250) -> int:
    files = sorted(glob.glob(f"{run_dir}/events.out.tfevents.*"))
    if not files:
        print(f"degcheck: no tfevents in {run_dir}")
        return 1
    ea = EventAccumulator(files[-1]); ea.Reload()
    err = at(ea, "Metrics/twist/error_vel_xy", kill_step)
    err100 = at(ea, "Metrics/twist/error_vel_xy", 100)
    track = at(ea, "Episode_Reward/track_linear_velocity", kill_step)
    if err is None or err100 is None or track is None:
        print(f"degcheck: not enough data yet (need iter {kill_step})")
        return 1
    growth = err / err100 if err100 else 0.0
    degenerate = err >= 1.8 * err100 and track < 0.02
    verdict = "DEGENERATE — KILL THE RUN" if degenerate else "healthy"
    print(f"degcheck: error_vel {err100:.3f}@100 -> {err:.3f}@{kill_step} (x{growth:.2f}), track {track:.3f} => {verdict}")
    return 42 if degenerate else 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: degcheck.py <run_dir> [kill_step=250]"); sys.exit(3)
    sys.exit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 250))
