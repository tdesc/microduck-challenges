#!/usr/bin/env python3
"""Render one Sock Heist run to mp4 (landscape), directly from MuJoCo frames.

Usage: render_clip.py <policy.onnx> [speed=1.2] [seed=5] [out=clip.mp4]
Uses the Arena's own runner (arena.runner.run_once) — the same physics the
server judges with — and mujoco.Renderer for offscreen frames.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/Users/valentin.kalinin/workspace/external/microduck-challenges/.venv/lib/python3.12/site-packages")

from arena.course import compile_course
from arena.lights import timetable
from arena.manifest import load_event
from arena.policy import load_policy
from arena.runner import run_once

EVENT = "sock-heist-6m"

def main():
    onnx = sys.argv[1]
    speed = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    out = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("clip.mp4")

    manifest = load_event(EVENT)
    policy = load_policy(onnx)
    course = compile_course(manifest)

    # try offscreen GL contexts in order
    renderer = None
    try:
        from mujoco import Renderer as MjRenderer
        import mujoco

        for backend in ("osmesa", "egl", "glfw"):
            os.environ_set = None
            try:
                if backend == "osmesa":
                    os.environ["MUJOCO_GL"] = "osmesa"
                elif backend == "egl":
                    os.environ["MUJOCO_GL"] = "egl"
                renderer = MjRenderer(course.model, height=480, width=854)
                print("GL backend:", backend)
                break
            except Exception as e:
                renderer = None
                print(f"backend {backend} failed: {str(e)[:80]}")
        if renderer is None:
            raise SystemExit("no offscreen GL available")
    except ImportError as e:
        raise SystemExit(f"mujoco import failed: {e}")

    import imageio

    writer = imageio.get_writer(out, fps=50, macro_block_size=1)
    outcome = run_once(
        policy,
        manifest,
        course,
        speed=speed,
        seed=seed,
        on_step=lambda sim_state: None,
        render_hook=lambda data: writer.append_data(renderer.render()),
    ) if "render_hook" in run_once.__code__.co_varnames else None
    if outcome is None:
        raise SystemExit("run_once has no render_hook — inspect signature: " + str(run_once.__code__.co_varnames))
    writer.close()
    print("wrote", out, "| status:", outcome.status if hasattr(outcome, "status") else "?")

if __name__ == "__main__":
    main()
