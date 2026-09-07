#!/usr/bin/env python3
"""Artifact-age drift alert: hard-fail (>1) if any interchange artifact is
older than 8 days (DESIGN_meta_catalog §6). Reads data/meta/stats.json."""
import datetime
import json
import sys
from pathlib import Path

MAX_AGE_DAYS = 8
STATS = Path(__file__).resolve().parent.parent / "data" / "meta" / "stats.json"


def main() -> int:
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc)
    failed = False
    for name, header in stats.get("inputs", {}).items():
        emitted = header.get("emitted_at")
        if not emitted:
            print(f"DRIFT: {name} has no emitted_at header")
            failed = True
            continue
        age = (now - datetime.datetime.fromisoformat(emitted)).days
        if age > MAX_AGE_DAYS:
            print(f"DRIFT: {name} artifact is {age} days old (> {MAX_AGE_DAYS})")
            failed = True
        else:
            print(f"OK: {name} artifact is {age} days old")
    if failed:
        return 1
    print("artifact ages OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
