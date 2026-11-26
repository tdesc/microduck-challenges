#!/usr/bin/env python3
"""Duck Glass Factory: стеклянный поток + Mission Control распределённых дуг.

Собирает состояние обеих машин (Pro локально, Air по ssh), издаёт glass-события
(colony.glass.duck_event.v1) в duck_glass.jsonl и перегенерирует Mission Control
(mission_control.html). Роли по контракту glass_factory: zcode=координатор,
машины=исполнители, судьи=оценщики, спонсор=власть.

Usage: duck_glass_factory.py [--once | --loop [сек]]
"""
import json, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/Users/valentin.kalinin/workspace/external/microduck-challenges")
GLASS = REPO / "duck_receipts" / "duck_glass.jsonl"
MISSION = REPO / "duck_receipts" / "mission_control.html"
AIR = "valentin@192.168.0.80"
AIR_HOME = "/Users/tdesc"

def sh(cmd, timeout=60):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout).stdout
    except Exception as e:
        return f"ERR {e}"

def collect_pro():
    out = {}
    out["actor_reward"] = sh("grep -E 'Mean reward' /tmp/talent_actor1.log | awk '{print $NF}' | tail -1").strip()
    out["actor_iter"] = sh("grep -E 'Learning iteration' /tmp/talent_actor1.log | tail -1 | grep -oE '[0-9]+/[0-9]+'").strip()
    out["scene_last"] = sh("tail -4 /tmp/actor_scenes.log 2>/dev/null | head -4").strip()
    out["chain_head"] = sh("/Users/valentin.kalinin/.pyenv/versions/3.11.11/bin/python3 scripts/duck/outcome_receipt.py verify | tail -1").strip()
    out["load"] = sh("uptime | grep -oE 'load averages[^]*' | head -c 40").strip()
    return out

def collect_air():
    s = sh(f"ssh -o BatchMode=yes -o ConnectTimeout=8 {AIR} 'bash -lc \""
           f"grep -E \\\"Learning iteration\\\" /tmp/talent_actor2.log 2>/dev/null | tail -1 | grep -oE \\\"[0-9]+/[0-9]+\\\"; "
           f"grep -E \\\"Mean reward\\\" /tmp/talent_actor2.log 2>/dev/null | awk '{{print \\$NF}}' | tail -1; "
           f"tail -2 /tmp/actor2_obedience.log 2>/dev/null; "
           f"grep -E \\\"Learning iteration\\\" /tmp/roller_air1.log 2>/dev/null | tail -1 | grep -oE \\\"[0-9]+/[0-9]+\\\"; "
           f"tail -2 /tmp/roller_judge_v3.log 2>/dev/null; "
           f"pmset -g batt | head -1\"'", timeout=45)
    lines = [l for l in s.splitlines() if l.strip()]
    return {"air_raw": lines}

def events(state):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ev = []
    ev.append({"schema": "colony.glass.duck_event.v1", "ts": ts, "machine": "pro",
               "kind": "training", "run": "talent_actor1", "iter": state.get("actor_iter", ""),
               "reward": state.get("actor_reward", ""), "note": "актёр sit/stand/head — школа окончена, REFUTED задокументирован"})
    ev.append({"schema": "colony.glass.duck_event.v1", "ts": ts, "machine": "pro",
               "kind": "gate", "note": state.get("scene_last", "")[:200]})
    ev.append({"schema": "colony.glass.duck_event.v1", "ts": ts, "machine": "air",
               "kind": "training", "run": "talent_actor2+roller_air1", "note": json.dumps(state.get("air_raw", []), ensure_ascii=False)[:300]})
    ev.append({"schema": "colony.glass.duck_event.v1", "ts": ts, "machine": "pro",
               "kind": "receipt_chain", "note": state.get("chain_head", "")})
    return ev

def mission(state, evs):
    air = state.get("air_raw", [])
    rows = "".join(f"<tr><td>{i+1}</td><td>{l}</td></tr>" for i, l in enumerate(air))
    ev_rows = "".join(f"<tr><td>{e['machine']}</td><td>{e['kind']}</td><td>{e.get('run','')}</td><td>{e['note'][:160]}</td></tr>" for e in evs)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Duck Mission Control</title>
<style>body{{background:#101218;color:#e8ebf0;font-family:Menlo,monospace;margin:24px}}
h1{{color:#ffd054}} h2{{color:#64a0ff}} table{{border-collapse:collapse;width:100%}}
td{{border:1px solid #2c303c;padding:6px 10px}} .ok{{color:#7ee787}} .warn{{color:#ffa657}}</style></head><body>
<h1>🦆 DUCK MISSION CONTROL — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</h1>
<h2>Колония в работе (оркестратор :9090 ready) · Протокол DUCK_CORTEX_SLOT v2</h2>
<h2>AIR — распределённый исполнитель (valentin@192.168.0.80, AC)</h2>
<table>{rows}</table>
<h2>PRO — координатор и школа (talent_actor1 завершён; рефлексы в цепи)</h2>
<p>actor: iter={state.get('actor_iter','?')} reward={state.get('actor_reward','?')} | {state.get('load','')}</p>
<pre style="white-space:pre-wrap">{state.get('scene_last','')}</pre>
<h2>СТЕКЛЯННЫЙ ПОТОК (последние события)</h2>
<table><tr><th>машина</th><th>тип</th><th>забег</th><th>заметка</th></tr>{ev_rows}</table>
<h2>ЦЕПЬ КВИТАНЦИЙ</h2><p class="ok">{state.get('chain_head','')}</p>
</body></html>"""

def cycle():
    state = {**collect_pro(), **collect_air()}
    evs = events(state)
    with open(GLASS, "a") as fh:
        for e in evs:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    MISSION.write_text(mission(state, evs))
    print(f"[{datetime.now().strftime('%H:%M:%S')}] glass+{len(evs)} events, mission control обновлён")

if __name__ == "__main__":
    cycle()  # один цикл за вызов; периодичность — планировщик/автомат
