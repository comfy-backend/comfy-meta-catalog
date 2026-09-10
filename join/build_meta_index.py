#!/usr/bin/env python3
"""build_meta_index.py — the meta-catalog joiner (FINGERPRINT/INTERCHANGE
specs v1, DESIGN_meta_catalog.md v2 §5).

Reads interchange artifacts from data/inbox/*.jsonl(.gz), joins them into
data/meta/:
  - meta_index.jsonl    one row per entity (platforms map + fingerprint +
                        quality + guards status)
  - entity_registry.jsonl  append-only entity state (git-is-the-disk)
  - related_network.jsonl  cross-cluster similarity edges
  - stats.json          join diagnostics incl. the LOUD collision report

Merge rules (v2 — the Jaccard tier was de-vacuated):
  auto-merge iff: same fp_bag AND |node_count diff| <= 2 AND cluster
  size <= 4 AND distinct node types >= 8 AND no single platform
  contributes >= 3 members (same-platform re-publish guard, RH pre-study
  2026-09-10). Anything else -> status "review"
  (never silently merged).

Stdlib only. Deterministic: output sorted by entity_id.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

FP_SPEC_SUPPORTED = 1
MIN_DISTINCT_TYPES = 8
MAX_NODE_COUNT_DIFF = 2
MAX_CLUSTER_SIZE = 4
# Same-platform multiplicity cap (RH 1k pre-study, session #10 —
# spec/RH_PRESTUDY_FINDINGS.md): measured clusters of 3-5 RH workflows
# sharing a bag are a RE-PUBLISH pattern, not a cross-platform identity
# signal. >=3 members on ONE platform routes to review even when the
# entropy guards pass. Cross-platform pairs (max 2 per platform) keep
# the current rules.
MAX_SAME_PLATFORM_CLUSTER = 3

# PLATFORM_REGISTRY ordinals (id derivation order)
ORDINALS = {"comfy_gallery": 1, "comfy_github": 2, "runninghub": 3, "rh_app": 4}
ENUMS = {
    "source_domain": {"ai", "cn", "both"},
    "ready": {"ready_to_run", "not_ready", "uncertain"},
    "model_status": {"bring_your_own", "no_models", "rh_hosted_likely", "rh_hosted_verified"},
}

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INBOX = ROOT / "data" / "inbox"
META = ROOT / "data" / "meta"


# ---------------------------------------------------------------- reading


def read_interchange(path: Path) -> tuple[dict, list[dict]]:
    opener = gzip.open if path.suffix == ".gz" else open
    rows = []
    header = None
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("header"):
                header = row
            else:
                rows.append(row)
    if header is None:
        raise ValueError(f"{path}: missing header row")
    if header.get("fp_spec") != FP_SPEC_SUPPORTED:
        raise ValueError(
            f"{path}: fp_spec {header.get('fp_spec')} != supported {FP_SPEC_SUPPORTED} — vendors must re-emit"
        )
    for row in rows:
        _validate_row(path, row)
    return header, rows


def _validate_row(path: Path, row: dict) -> None:
    platform = row.get("platform")
    if platform not in ORDINALS:
        raise ValueError(f"{path}: unknown platform {platform!r}")
    for field, allowed in ENUMS.items():
        v = row.get(field)
        if v is not None and v not in allowed:
            raise ValueError(f"{path}: bad {field}={v!r} (allowed: {sorted(allowed)})")
    if not row.get("ids"):
        raise ValueError(f"{path}: row missing ids map")


# ---------------------------------------------------------------- entities


def primary_id(row: dict) -> tuple[int, str]:
    """(ordinal, platform_id) — the smallest wins (entity-id derivation)."""
    best = None
    for key, pid in sorted(row["ids"].items()):
        if key in ORDINALS:
            cand = (ORDINALS[key], str(pid))
            if best is None or cand < best:
                best = cand
    if best is None:
        raise ValueError(f"row ids map has no registered platform: {row['ids']!r}")
    return best


def entity_id_for(first: tuple[int, str]) -> str:
    platform_key = next(k for k, o in ORDINALS.items() if o == first[0])
    return "mw_" + hashlib.sha256(f"v1|{platform_key}|{first[1]}".encode()).hexdigest()[:16]


def cross_log_score(members: list[dict]) -> float | None:
    total = 0.0
    seen = False
    for row in members:
        ls = (row.get("engagement") or {}).get("log_score")
        if ls is not None:
            total += float(ls)
            seen = True
    return round(total, 4) if seen else None


# ---------------------------------------------------------------- join


def build(inbox: Path = INBOX, meta_dir: Path = META) -> dict:
    paths = sorted(list(inbox.glob("*.jsonl")) + list(inbox.glob("*.jsonl.gz")))
    if not paths:
        raise SystemExit(f"no interchange artifacts in {inbox} — vendors have not emitted yet (v0 state)")

    headers, rows = {}, []
    for p in paths:
        h, r = read_interchange(p)
        headers[p.name] = h
        rows.extend(r)

    # --- cluster by fp_bag
    by_bag: dict[str, list[dict]] = defaultdict(list)
    null_fp_rows = []
    for row in rows:
        fp = row.get("fp_bag")
        if fp is None:
            null_fp_rows.append(row)
        else:
            by_bag[fp].append(row)

    registry_path = meta_dir / "entity_registry.jsonl"
    registry = _load_registry(registry_path)

    entities = {}  # entity_id -> {platforms, members, fp, status}
    review_queue = []
    for fp, members in sorted(by_bag.items()):
        distinct_types = set()
        for m in members:
            distinct_types.update(m.get("node_types") or [])
        counts = [m.get("node_count") or 0 for m in members]
        platform_counts: dict[str, int] = defaultdict(int)
        for m in members:
            platform_counts[m.get("platform") or "?"] += 1
        guards_ok = (
            len(members) <= MAX_CLUSTER_SIZE
            and (max(counts) - min(counts)) <= MAX_NODE_COUNT_DIFF
            and len(distinct_types) >= MIN_DISTINCT_TYPES
            and max(platform_counts.values()) < MAX_SAME_PLATFORM_CLUSTER
        )
        if not guards_ok:
            review_queue.append({"fp_bag": fp, "members": [m["ids"] for m in members]})
            # guards failed -> NEVER merge; each member becomes its own entity
            for m in members:
                eid = _entity_for_row(m, registry, entities)
                entities[eid]["members"].append(m)
                entities[eid]["status"] = "single"
        elif len(members) > 1:
            # merged cluster: ONE entity for ALL members, keyed on the
            # cluster's smallest (ordinal, platform_id) — review-corrected
            # semantics (the v1 draft's per-row assignment was a bug caught
            # by the smoke test)
            first = min(primary_id(m) for m in members)
            eid = entity_id_for(first)
            if eid not in entities:
                entities[eid] = {"members": [], "status": "merged", "first_seen": _now_iso()}
            for m in members:
                entities[eid]["members"].append(m)
            entities[eid]["status"] = "merged"
        else:
            m = members[0]
            eid = _entity_for_row(m, registry, entities)
            entities[eid]["members"].append(m)
            entities[eid]["status"] = "single"
    for m in null_fp_rows:
        eid = _entity_for_row(m, registry, entities)
        entities[eid]["members"].append(m)
        entities[eid]["status"] = "single"  # no fingerprint — never merged

    # --- write outputs
    meta_dir.mkdir(parents=True, exist_ok=True)
    out_rows = []
    for eid, ent in sorted(entities.items()):
        members = sorted(ent["members"], key=primary_id)
        platforms = {}
        for m in members:
            for k, v in m["ids"].items():
                entry = platforms.setdefault(k, {"ids": [], "engagement": []})
                entry["ids"].append(str(v))
                entry["engagement"].append(m.get("engagement"))
        first_member = members[0]
        fp = first_member.get("fp_bag")
        out_rows.append(
            {
                "entity_id": eid,
                "status": ent["status"],
                "platforms": {
                    k: {"ids": v["ids"], "engagement": v["engagement"][0] or None}
                    for k, v in platforms.items()
                },
                "members": [
                    {
                        "platform": m["platform"],
                        "ids": m["ids"],
                        "name": m.get("name"),
                        "engagement": m.get("engagement"),
                        "url": m.get("url"),
                    }
                    for m in members
                ],
                "fingerprint": {
                    "fp_spec": FP_SPEC_SUPPORTED,
                    "fp_bag": fp,
                    "node_count": first_member.get("node_count"),
                    "node_types": first_member.get("node_types"),
                },
                "name": first_member.get("name"),
                "cross_log_score": cross_log_score(members),
                "ready": {m["platform"]: m.get("ready") for m in members if m.get("ready")},
                "urls": {m["platform"]: m.get("url") for m in members if m.get("url")},
                "updated_at": max(m.get("updated_at") or "" for m in members),
            }
        )
    _write_jsonl(meta_dir / "meta_index.jsonl", out_rows)

    related = _related_edges(rows)
    _write_jsonl(meta_dir / "related_network.jsonl", related)

    _append_registry(registry_path, entities)

    stats = {
        "run_at": _now_iso(),
        "inputs": headers,
        "rows_in": len(rows),
        "entities": len(entities),
        "merged_entities": sum(1 for e in entities.values() if e["status"] == "merged"),
        "review_queue": review_queue,
        "null_fp_rows": len(null_fp_rows),
        "bag_groups": len(by_bag),
        "duplicate_groups": sum(1 for ms in by_bag.values() if len(ms) > 1),
        "related_edges": len(related),
        "collision_report": {
            "dup_group_count": sum(1 for ms in by_bag.values() if len(ms) > 1),
            "largest_groups": sorted(
                ({"fp_bag": fp, "size": len(ms)} for fp, ms in by_bag.items() if len(ms) > 1),
                key=lambda g: -g["size"],
            )[:10],
            "note": "review queue = clusters failing guards (cluster>4 | node_count diff>2 | distinct<8 | same-platform>=3); never auto-merged",
        },
    }
    (meta_dir / "stats.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
    return stats


# ---------------------------------------------------------------- helpers


def _entity_for_row(row: dict, registry: dict, entities: dict) -> str:
    first = primary_id(row)
    eid = entity_id_for(first)
    if eid not in entities:
        entities[eid] = {"members": [], "status": "single", "first_seen": _now_iso()}
    return eid


def _related_edges(rows: list[dict]) -> list[dict]:
    """Cross-cluster related edges: inverted index over node types; candidate
    pairs sharing >= max(6, 60% of smaller set); Jaccard over type SETS;
    >=0.8 strong, 0.5-0.8 weak. Never a merge."""
    sets_by_row = {}
    for i, row in enumerate(rows):
        types = set(row.get("node_types") or [])
        if len(types) >= 3:
            sets_by_row[i] = types
    index = defaultdict(set)
    for i, types in sets_by_row.items():
        for t in types:
            index[t].add(i)
    edges = []
    seen_pairs = set()
    for i, types in sorted(sets_by_row.items()):
        shared = defaultdict(int)
        for t in types:
            for j in index[t]:
                if j != i:
                    shared[j] += 1
        for j, overlap in shared.items():
            pair = (min(i, j), max(i, j))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            smaller = min(len(types), len(sets_by_row[j]))
            if overlap >= max(6, int(0.6 * smaller)):
                jac = overlap / len(types | sets_by_row[j])
                if jac >= 0.5:
                    a, b = rows[pair[0]], rows[pair[1]]
                    if a.get("fp_bag") == b.get("fp_bag"):
                        continue  # same cluster — not a related edge
                    edges.append(
                        {
                            "a": {"ids": a["ids"], "fp_bag": a.get("fp_bag")},
                            "b": {"ids": b["ids"], "fp_bag": b.get("fp_bag")},
                            "jaccard": round(jac, 4),
                            "strength": "strong" if jac >= 0.8 else "weak",
                        }
                    )
    return sorted(edges, key=lambda e: -e["jaccard"])[:10000]


def _load_registry(path: Path) -> dict:
    if not path.exists():
        return {}
    reg = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            reg[r["entity_id"]] = r
    return reg


def _append_registry(path: Path, entities: dict) -> None:
    """Append-only: one revision row per entity per run (update-in-place
    forbidden). The joiner replays the file for state."""
    now = _now_iso()
    with open(path, "a", encoding="utf-8") as f:
        for eid, ent in sorted(entities.items()):
            f.write(
                json.dumps(
                    {
                        "entity_id": eid,
                        "revision_at": now,
                        "platforms": sorted(
                            {k for m in ent["members"] for k in m["ids"]}
                        ),
                        "fp_bag": next((m.get("fp_bag") for m in ent["members"] if m.get("fp_bag")), None),
                        "status": ent["status"],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")


def _now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    stats = build()
    print(json.dumps(stats, indent=1))
