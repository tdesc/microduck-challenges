#!/usr/bin/env python3
"""Гейт-верификатор сцен талант-шоу: проигрывает сцену через физику арены,
снимает trace и печатает PASS/FAIL по гейтгардам (TALENT_SHOW_PIPELINE.md).

Usage: show_gates.py <policy.onnx> [--scene S0|S1|S2|S3|S4|S5|ALL]
Exit 0 = все сцены PASS, 1 = есть FAIL.
"""
import sys
from pathlib import Path
sys.path.insert(0, "/Users/valentin.kalinin/workspace/external/microduck-challenges/.venv/lib/python3.12/site-packages")
import os
import numpy as np
import imageio

from arena.manifest import load_event
from arena.timeline import load_troupe
from arena.cast import cast_of, load_borrowed
from arena.course import _troupe, _posed
from arena.policy import load_policy
from arena.constants import CTRL_DT
from arena import runner as ar
import mujoco

STAND_Z, SIT_Z, FALL_Z = 0.115, 0.060, 0.045

SCENES = {
 "S0": {"dur": 4.0, "kf": [
    {"t": 0.0, "twist": [0.6, 0, 0]},
    {"t": 1.2, "twist": [0, 0, 0], "head": [0.3, 0.1, 0, 0]},
    {"t": 3.9}]},
 "S1": {"dur": 5.5, "kf": [
    {"t": 0.0},
    {"t": 0.3, "twist": [1, 0, 0]},
    {"t": 5.4, "twist": [1, 0, 0]}]},
 "S2": {"dur": 7.0, "kf": [
    {"t": 0.0, "twist": [1, 0, 0]},
    {"t": 1.5, "twist": [0, 0, 0], "triggers": [0.8, 0]},
    {"t": 1.9},
    {"t": 6.9}]},
 "S3": {"dur": 13.0, "kf": [
    {"t": 0.0},
    {"t": 1.0, "head": [0.15, 0, 0.45, 0.1]},
    {"t": 2.5, "head": [0.15, 0, -0.45, 0.1]},
    {"t": 4.0, "head": [0.15, 0, 0.45, 0.1]},
    {"t": 5.5, "head": [0.15, 0, -0.45, 0.1]},
    {"t": 7.0, "head": [0.15, 0, 0.45, 0.1]},
    {"t": 8.5, "head": [0.15, 0, -0.45, 0.1]},
    {"t": 10.0, "head": [0.15, 0, 0.45, 0.1]},
    {"t": 11.5, "head": [0.15, 0, -0.45, 0.1]},
    {"t": 12.9}]},
 "S4": {"dur": 16.0, "kf": [
    {"t": 0.0}, {"t": 1.0, "twist": [1, 0, 0]}, {"t": 1.35, "twist": [0, 0, 0]},
    {"t": 2.0, "twist": [1, 0, 0]}, {"t": 2.35, "twist": [0, 0, 0]},
    {"t": 3.0, "twist": [1, 0, 0]}, {"t": 3.35, "twist": [0, 0, 0]},
    {"t": 4.0, "twist": [1, 0, 0]}, {"t": 4.35, "twist": [0, 0, 0]},
    {"t": 5.0, "twist": [1, 0, 0]}, {"t": 5.35, "twist": [0, 0, 0]},
    {"t": 15.9}]},
 "S5": {"dur": 20.0, "kf": [
    {"t": 0.0},
    {"t": 0.5, "head": [0.15, 0.1, 0.3, 0], "triggers": [0, 0.95]},
    {"t": 2.5, "head": [0.15, 0.1, -0.3, 0], "triggers": [0, 0.95]},
    {"t": 3.5, "head": [0.5, 0.25, 0, 0]},
    {"t": 19.8, "head": [0.5, 0.25, 0, 0]},
    {"t": 19.95}]},
}

def run_scene(policy, sid):
    manifest = load_event("got-a-talent")
    tl = {"timeline_version": 1, "duration_s": SCENES[sid]["dur"], "keyframes": SCENES[sid]["kf"]}
    tmp = Path(f"/tmp/show_scene_{sid}.json"); tmp.write_text(__import__("json").dumps(tl, ensure_ascii=False))
    troupe = load_troupe(tmp, manifest)
    cast = cast_of(manifest, troupe, load_policy(policy), None, load_borrowed(troupe, {}))
    perf = cast.performers
    spec = _troupe(manifest, [(p.rig, p.start) for p in perf])
    spec.worldbody.add_light(pos=[0.0, 0.0, 2.0], dir=[0.0, 0.0, -1.0],
                             diffuse=[0.9, 0.9, 0.85], ambient=[0.3, 0.3, 0.3])
    model = _posed(spec.compile(), manifest, [(p.rig, p.start) for p in perf])
    steps = round(SCENES[sid]["dur"] / CTRL_DT)
    trace = np.empty((1, steps, 7 + 60), dtype=np.float32)
    sim, settle, _ = ar._start(manifest, model, [p.policy for p in perf],
                               [p.start.yaw_deg for p in perf], 1, ar._commands(perf, 0.0))
    status = "finish"
    for k in range(steps):
        sim.step(ar._commands(perf, k * CTRL_DT))
        if ar._reset_by_mujoco(sim.data):
            status, trace = f"fall at {k*CTRL_DT:.2f}s", None
            break
        sim.record(trace[:, k])
    return status, trace

def gates(sid, status, trace):
    if trace is None:
        return {f"G{sid[1:]}_nofall": (False, status)}
    z = trace[0, :, 2]; xy = trace[0, :, :2]
    fps = round(1 / CTRL_DT)
    res = {}
    def frac_lo(a, b, thr): w = z[a*fps:min(b, len(z))]; return float((w < thr).mean()) if len(w) else 0.0
    def frac_hi(a, b, thr): w = z[a*fps:min(b, len(z))]; return float((w >= thr).mean()) if len(w) else 0.0
    nofall = ("нет падения", z.min() >= FALL_Z)
    if sid == "S0":
        d = float(np.linalg.norm(xy[min(int(1.2*fps), len(xy)-1)] - xy[0]))
        res["G0_прошёл_0.25м"] = (d >= 0.25, round(d, 3))
        res["G0_no_fall"] = nofall
    if sid == "S1":
        f = frac_lo(int(2.2*fps), min(int(5.4*fps), len(z)-1), 0.085)
        res["G1_сидел_80%"] = (f >= 0.8, round(f, 2))
        res["G1_no_fall"] = nofall
    if sid == "S2":
        f = frac_hi(int(6.0*fps), min(int(6.9*fps), len(z)-1), 0.105)
        res["G2_встал_70%"] = (f >= 0.7, round(f, 2))
        res["G2_no_fall"] = nofall
    if sid == "S3":
        drift = float(np.linalg.norm(xy[min(int(12.9*fps), len(xy)-1)] - xy[int(7.0*fps)]))
        res["G3_дрейф_0.12"] = (drift <= 0.12, round(drift, 3))
        res["G3_no_fall"] = nofall
    if sid == "S4":
        dips = int((np.diff((z[int(13.0*fps):min(int(16.0*fps), len(z)-1)] < 0.09).astype(int)) == 1).sum())
        res["G4_прыжки_2+"] = (dips >= 2, dips)
        res["G4_no_fall"] = nofall
    if sid == "S5":
        tail = z[-fps:]
        res["G5_финал_стабилен"] = (float(tail.std()) < 0.01, round(float(tail.std()), 4))
        res["G5_no_fall"] = nofall
    return res

def main():
    policy = sys.argv[1]
    only = sys.argv[sys.argv.index("--scene")+1] if "--scene" in sys.argv else "ALL"
    ids = list(SCENES) if only == "ALL" else [only]
    allpass = True
    for sid in ids:
        status, trace = run_scene(policy, sid)
        res = gates(sid, status, trace)
        passed = all(ok for ok, _ in res.values())
        allpass &= passed
        print(f"=== {sid} [{status}] {'PASS' if passed else 'FAIL'}")
        for name, (ok, val) in res.items():
            print(f"   {'✅' if ok else '❌'} {name}: {val}")
    print("ИТОГ:", "ВСЕ ГЕЙТЫ ЗЕЛЁНЫЕ" if allpass else "ЕСТЬ ПРОВАЛЫ — сцены(а) в сборку не идёт(ут)")
    return 0 if allpass else 1

if __name__ == "__main__":
    sys.exit(main())
