# 🦆 tdesc on the Microduck Arena

Three boards entered, all from an 8-core Mac (CPU-only PPO, no GPU):

| Board | Policy | Result | Repo |
|---|---|---|---|
| **Sock Heist 6m** | heist1 (from scratch) | **15.667 s · 5/5 seeds · zero catches** | [microduck-sock-heist-heist1](https://huggingface.co/tdesc/microduck-sock-heist-heist1) (clips included) |
| **2m Sprint** | warmstart0 (ref walker warm-start) | **4.982 s · 5/5 seeds** | [microduck-sprint-warmstart0](https://huggingface.co/tdesc/microduck-sprint-warmstart0) |
| **Got a Talent** | quack-sonata (timeline performance) | **106th place · 110 pts** | [microduck-quack-sonata](https://huggingface.co/tdesc/microduck-quack-sonata) (clips included) |

Every repo ships with clips (`clips/`), the training recipe (commit + seed + command in the model card), and honest disclaimers. The arena confirms all numbers server-side.

*Genuine quacks: warm-start disclaimers where applicable; seeds diverge (t16 never found the pull); a statue run taught us more than a lucky one.*
