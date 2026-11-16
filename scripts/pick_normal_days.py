"""Pick the ordinary days used for the false-alert rate, reproducibly.

Draws from the DMA daily files (2024-03-01 to 2025-02-26; earlier periods are monthly
files only), 2 or 3 days from every month so each season is represented, and never a
day within one day of a reported incident. Seeded, so rerunning gives the same list.
Writes data/reference/normal_days.txt (one YYYY-MM-DD per line, sorted).
"""
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 20261116
N_EXTRA = 30
# Days already in the study (tuning day and the first four ordinary days) and incident days.
EXISTING = {"2024-04-10", "2024-06-12", "2024-08-14", "2024-10-09", "2025-02-12"}
INCIDENTS = ["2024-11-17", "2024-11-18", "2024-12-25", "2025-01-26"]

index = json.loads((ROOT / "data/raw/_s3_index_2022_2026.json").read_text())
daily = sorted(m.group(1) for k, _ in index if (m := re.search(r"aisdk-(\d{4}-\d{2}-\d{2})\.zip", k)))
blocked = set(EXISTING)
for d in INCIDENTS:
    x = date.fromisoformat(d)
    blocked |= {(x + timedelta(days=k)).isoformat() for k in (-1, 0, 1)}
by_month: dict[str, list[str]] = {}
for d in daily:
    if d not in blocked:
        by_month.setdefault(d[:7], []).append(d)
rng = random.Random(SEED)
months = sorted(by_month)
quota = {m: N_EXTRA // len(months) for m in months}
for m in rng.sample(months, N_EXTRA - sum(quota.values())):
    quota[m] += 1
picked = sorted(d for m in months for d in rng.sample(by_month[m], quota[m]))
(ROOT / "data/reference/normal_days.txt").write_text("\n".join(sorted(EXISTING | set(picked))) + "\n")
print(len(picked), "new days;", len(EXISTING | set(picked)), "in the list")
print(" ".join(picked))
