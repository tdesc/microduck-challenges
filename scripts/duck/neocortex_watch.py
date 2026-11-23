#!/usr/bin/env python3
"""Neocortex watcher — live post-peak decay guard for a training run.

Lesson of 2026-11-23 (tug_now): the duck peaked at iter ~60-100 (first wins),
the peak was never banked (save_interval=250), and by iter 169 it was sliding
(in_pit 37.5%, wins gone). The morning judge is too late: the neocortex must
watch DURING the run and act at the peak's end.

Rule: poll the live tfevents every POLL_S seconds. Track the running max of the
win reward. If win drops below DROP_FRACTION of the running max (max at least
MIN_PEAK) for K consecutive polls after the peak, kill the training process
(SIGTERM) and append a kill receipt via outcome_receipt.py — the best banked
checkpoint (<= save-interval old) is the champion.

Usage: neocortex_watch.py <run_dir> <train_pid> [--event tug-of-war] [--poll 60]
                          [--min-peak 0.005] [--drop 0.25] [--k 3]
"""
import glob, os, signal, sys, time
from pathlib import Path

sys.path.insert(0, "/Users/valentin.kalinin/workspace/external/microduck-challenges/.venv/lib/python3.12/site-packages")
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

WIN_TAG = "Episode_Reward/win"
POLL_S = 60


def latest_win(run_dir: str):
    files = sorted(glob.glob(f"{run_dir}/events.out.tfevents.*"))
    if not files:
        return None, 0
    ea = EventAccumulator(files[-1]); ea.Reload()
    if WIN_TAG not in ea.Tags()["scalars"]:
        return None, 0
    ev = ea.Scalars(WIN_TAG)
    if not ev:
        return None, 0
    return ev[-1].value, ev[-1].step


def main():
    run_dir = sys.argv[1]
    pid = int(sys.argv[2])
    min_peak = float(sys.argv[4]) if len(sys.argv) > 4 else 0.005
    drop = float(sys.argv[5]) if len(sys.argv) > 5 else 0.25
    k_needed = int(sys.argv[6]) if len(sys.argv) > 6 else 3

    peak = 0.0
    peak_step = 0
    low_streak = 0
    while True:
        win, step = latest_win(run_dir)
        if win is None:
            time.sleep(POLL_S); continue
        if win > peak:
            peak, peak_step = win, step
            low_streak = 0
        elif peak >= min_peak and win < drop * peak:
            low_streak += 1
            print(f"[watch] post-peak decay: win {win:.4f} < {drop}*peak {peak:.4f} "
                  f"(streak {low_streak}/{k_needed}, peak was at iter {peak_step})", flush=True)
            if low_streak >= k_needed:
                print(f"[watch] KILL: peak at iter {peak_step} was not improving; "
                      f"saving is done by the trainer's own cadence — stopping the slide.", flush=True)
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                receipt = (
                    f'{{"schema":"colony.duck.watch_kill.v1","run_dir":"{run_dir}",'
                    f'"peak_step":{peak_step},"peak_win":{peak},"win_at_kill":{win},'
                    f'"ts":"{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}"}}\n'
                )
                with open(Path(run_dir).parent / "watch_kill.jsonl", "a") as fh:
                    fh.write(receipt)
                return 0
        else:
            low_streak = 0
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
