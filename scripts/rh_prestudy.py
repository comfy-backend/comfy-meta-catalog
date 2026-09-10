#!/usr/bin/env python3
"""RH 1k-sample bag-duplicate pre-study (T4 item 4, session #10).

WHY: the comfy corpus measured a 20% bag-collision rate (session #9 golden
fixtures — sd3.5_simple_example ≡ flux_schnell collide on identical node
bags). Before FINGERPRINT_SPEC v1 is FROZEN, the RH side needs the same
measurement: what fraction of RH exports share an identical bag fingerprint
with at least one other sampled workflow, and what do those collision
clusters look like (node counts, distinct-type counts, subgraph usage)?
Those numbers calibrate the meta joiner's merge guards for RH-sourced rows.

METHOD: draw a fixed-seed (42) random sample of N=1000 export files from the
RH data repo (blobless clone, blobs materialized via `git cat-file --batch`
— one process, lazy fetch from origin), fingerprint each with THE canonical
join/fingerprint.py, and aggregate.

Reproducibility: seed + data-repo HEAD SHA are embedded in the report. The
sample is over PATHS (workflow ids), stable for a given HEAD.

Usage (from a blobless clone of RH-workflow-data at <repo>):
    python3 scripts/rh_prestudy.py --repo <repo> [--n 1000] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "join"))
from fingerprint import compute_fp  # noqa: E402  (THE canonical implementation)


def list_export_blobs(repo: Path) -> list[tuple[str, str]]:
    """[(blob_sha, rel_path)] for every exports/**.comfyui.json at HEAD."""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "HEAD", "exports/"],
        capture_output=True, text=True, check=True,
    ).stdout
    blobs = []
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2 or not parts[1].endswith(".comfyui.json"):
            continue
        meta = parts[0].split()
        if len(meta) == 3 and meta[1] == "blob":
            blobs.append((meta[2], parts[1]))
    return blobs


def fetch_blobs(repo: Path, shas: list[str]) -> dict[str, bytes]:
    """Materialize blobs via one `git cat-file --batch` process.

    NOTE: on a blobless (filter=blob:none) clone the lazy promisor fetches
    are effectively one-HTTPS-round-trip-per-blob (~0.9s each — measured),
    so this path is only viable for tiny samples. The HTTP CDN path below
    (fetch_raw via raw.githubusercontent.com) parallelizes far better.
    """
    proc = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    payload = "".join(s + "\n" for s in shas)
    out, _ = proc.communicate(payload.encode(), timeout=600)
    blobs: dict[str, bytes] = {}
    pos = 0
    data = out
    while pos < len(data):
        nl = data.index(b"\n", pos)
        header = data[pos:nl].decode()
        parts = header.split()
        if len(parts) != 3 or parts[1] == "missing":
            pos = nl + 1
            continue
        sha, size = parts[0], int(parts[2])
        start = nl + 1
        blobs[sha] = data[start:start + size]
        pos = start + size + 1  # trailing newline after the blob
    return blobs


def fetch_raw(paths: list[str], token: str, workers: int = 12) -> dict[str, bytes]:
    """Parallel raw-file fetch from raw.githubusercontent.com (CDN-backed).

    ~0.9s/blob sequentially via git lazy-fetch; ~12 workers over the CDN
    brings 1000 files under a minute. Returns {rel_path: bytes}; missing
    files are simply absent.
    """
    import concurrent.futures
    import urllib.request

    base = "https://raw.githubusercontent.com/beulahkemp/RH-workflow-data/HEAD/"

    def one(path: str) -> tuple[str, bytes | None]:
        req = urllib.request.Request(
            base + path, headers={"Authorization": f"token {token}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return path, r.read()
        except Exception:
            return path, None

    out: dict[str, bytes] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for path, data in ex.map(one, paths):
            if data is not None:
                out[path] = data
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="path to a clone of RH-workflow-data")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=None, help="write JSON report to this path")
    args = ap.parse_args()
    repo = Path(args.repo)

    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    blobs = list_export_blobs(repo)
    rng = random.Random(args.seed)
    sample = rng.sample(blobs, min(args.n, len(blobs)))
    print(f"data repo HEAD: {head}")
    print(f"export files at HEAD: {len(blobs)}  |  sampling {len(sample)} (seed {args.seed})")

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("GITHUB_TOKEN env var required for the raw-file fetch (read scope)")
    raw = fetch_raw([p for _, p in sample], token)

    results = []           # per-workflow records
    parse_errors = 0
    empty_bags = 0
    for sha, path in sample:
        raw_bytes = raw.get(path)
        if raw_bytes is None:
            parse_errors += 1
            continue
        try:
            wf = json.loads(raw_bytes.decode("utf-8"))
            fp = compute_fp(wf)
        except Exception:
            parse_errors += 1
            continue
        if fp["fp_bag"] is None:
            empty_bags += 1
        results.append({
            "path": path,
            "workflow_id": Path(path).name.split(".")[0],
            **fp,
            "distinct_types": len(fp["node_types"]),
        })

    n = len(results)
    by_bag: dict[str | None, list[dict]] = defaultdict(list)
    for r in results:
        by_bag[r["fp_bag"]].append(r)

    distinct = len([b for b in by_bag if b is not None])
    colliding = [rs for b, rs in by_bag.items() if b is not None and len(rs) > 1]
    colliding_rows = sum(len(rs) for rs in colliding)
    dup_rate = colliding_rows / n if n else 0.0

    # Guard-calibration stats: for rows that share a bag, how different are
    # the node counts / distinct types? (Identical bags have identical
    # node_count and distinct_types BY CONSTRUCTION — fp_bag hashes the full
    # bag — so the interesting axis is cluster size and bag shape, not pair
    # diffs. Node-count diff matters for the Jaccard-tier, not the bag tier.)
    cluster_sizes = Counter(len(rs) for rs in colliding)
    top_clusters = sorted(
        (rs for rs in colliding), key=lambda rs: -len(rs)
    )[:10]
    top_shapes = [
        {
            "cluster_size": len(rs),
            "node_count": rs[0]["node_count"],
            "distinct_types": rs[0]["distinct_types"],
            "sample_ids": [r["workflow_id"] for r in rs[:4]],
            "types_head": rs[0]["node_types"][:6],
        }
        for rs in top_clusters
    ]

    # Bag-shape distribution over the whole sample (informs the low-entropy
    # guard: bags with very few distinct types are structurally trivial).
    type_counts = Counter(r["distinct_types"] for r in results)
    node_counts = sorted(r["node_count"] for r in results)
    dangling = sum(r["dangling_refs"] for r in results)
    cycles = sum(r["cycle_guards"] for r in results)

    report = {
        "study": "rh-1k-bag-duplicate-prestudy",
        "t4_item": "T4 item 4 — gates FINGERPRINT_SPEC v1 freeze",
        "data_repo_head": head,
        "seed": args.seed,
        "sampled": len(sample),
        "fingerprinted": n,
        "parse_errors": parse_errors,
        "empty_bags": empty_bags,
        "distinct_bags": distinct,
        "rows_sharing_a_bag": colliding_rows,
        "duplicate_rate": round(dup_rate, 4),
        "collision_clusters": len(colliding),
        "cluster_size_histogram": {str(k): v for k, v in sorted(cluster_sizes.items())},
        "distinct_types_histogram": {str(k): v for k, v in sorted(type_counts.items())},
        "node_count_median": node_counts[len(node_counts) // 2] if node_counts else None,
        "node_count_p90": node_counts[int(len(node_counts) * 0.9)] if node_counts else None,
        "subgraph_diag": {"dangling_refs_total": dangling, "cycle_guards_total": cycles},
        "top_collision_shapes": top_shapes,
    }

    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
