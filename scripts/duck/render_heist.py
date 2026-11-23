#!/usr/bin/env python3
"""Render a Sock Heist run to mp4: the Arena's own loop + cgl frames + imageio.

Usage: render_heist.py <policy.onnx> [speed=1.2] [seed=5] [out=out/heist_clip.mp4]
The loop is a faithful copy of arena.runner.run_once's stepping (same command
zeroing on reds, same steering, same fall/catch judging), with a mujoco.Renderer
frame captured every control step.
"""
import os, sys
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "cgl")
sys.path.insert(0, "/Users/valentin.kalinin/workspace/external/microduck-challenges/.venv/lib/python3.12/site-packages")

import numpy as np
import mujoco
from mujoco import Renderer

from arena import runner as R
from arena.course import compile_course
from arena.lights import timetable
from arena.manifest import load_event
from arena.policy import load_policy
from arena.runner import CTRL_DT

EVENT = "sock-heist-6m"
WORLD_DOWN = np.array([0.0, 0.0, -1.0])

def main():
    onnx = sys.argv[1]
    speed = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    out = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("out/heist_clip.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    policy = load_policy(onnx)
    manifest = load_event(EVENT)
    model = compile_course(manifest)
    command = np.asarray(manifest.command, dtype=np.float64)
    command[0] = speed

    sim, settle_data, _ = R._start(manifest, model, [policy], [0.0], seed, [command])
    data, adr = sim.data, sim.ducks[0].adr
    lights = manifest.lights
    stand = command.copy(); stand[0:3] = 0.0
    schedule = R._LightSteps.of(
        timetable(lights, manifest.id, seed, round(manifest.time_limit_s / CTRL_DT)),
        round(lights.turn_s / CTRL_DT), round(manifest.time_limit_s / CTRL_DT),
    ) if lights is not None else None
    steering = manifest.steering
    direction = R.ramp_dir(manifest.course.slope_deg) if hasattr(R, "ramp_dir") else np.array([1.0, 0.0, 0.0])
    start_progress = float(direction @ data.qpos[0:3])
    past_the_line = lambda: float(direction @ data.qpos[0:3]) - start_progress >= manifest.course.length_m
    max_steps = round(manifest.time_limit_s / CTRL_DT)
    fall_needed = round(manifest.termination.fall_hold_s / CTRL_DT)
    W, H = int(model.vis.global_.offwidth), int(model.vis.global_.offheight)
    vertical = os.environ.get("VERTICAL") == "1"
    vertical = os.environ.get("VERTICAL") == "1"
    renderer = Renderer(model, height=H, width=W)
    import imageio
    writer = imageio.get_writer(out, fps=round(1 / CTRL_DT), macro_block_size=1)

    tipped = 0
    status, time_s = "timeout", None
    for step in range(max_steps):
        if schedule is not None and schedule.red[step]:
            asked = stand
        elif steering is not None:
            asked = R._steered(steering, data, adr, command)
        else:
            asked = command
        if past_the_line():
            status, time_s = "finish", step * CTRL_DT
            frame = renderer.render()
            if vertical:
                import PIL.Image
                fw, fh, vw = frame.shape[1], frame.shape[0], int(frame.shape[0] * 9 / 16)
                x_m = float(data.qpos[0]) - start_progress
                cx = int(min(W - vw / 2 - 2, max(vw / 2 + 2, (x_m / 6.0) * W)))
                frame = np.asarray(PIL.Image.fromarray(frame).crop((cx - vw // 2, 0, cx + vw // 2, fh)))
            writer.append_data(frame)
            break
        crossing = sim.step([asked], None)
        frame = renderer.render()
        if vertical:
            import PIL.Image
            fw, fh, vw = frame.shape[1], frame.shape[0], int(frame.shape[0] * 9 / 16)
            x_m = float(data.qpos[0]) - start_progress
            cx = int(min(W - vw / 2 - 2, max(vw / 2 + 2, (x_m / 6.0) * W)))
            frame = PIL.Image.fromarray(frame).crop((cx - vw // 2, 0, cx + vw // 2, fh))
            frame = np.asarray(frame)
        writer.append_data(frame)
        if not np.all(np.isfinite(data.qpos)):
            status, time_s = "fall", step * CTRL_DT; break
        rotation = data.xmat[adr.trunk].reshape(3, 3)
        gravity_z = float((rotation.T @ WORLD_DOWN)[2])
        tipped = tipped + 1 if gravity_z > manifest.termination.fall_gravity_z else 0
        if tipped >= fall_needed:
            status, time_s = "fall", step * CTRL_DT; break
        if schedule is not None and schedule.red[step]:
            continue

    writer.close()
    print(f"rendered {out} | status={status} time={time_s}s reds={schedule and 'see timetable'}")

if __name__ == "__main__":
    main()
