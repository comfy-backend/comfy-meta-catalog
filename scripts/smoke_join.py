#!/usr/bin/env python3
"""Smoke-test the meta joiner: fabricate two tiny interchange artifacts from
REAL fixture fingerprints (including a known cross-platform collision),
run build + verify, assert expected outcomes, then clean up.

Proves at v0: header validation, fp-bag clustering, merge guards, review
queue, cross-platform merge (comfy <-> RH same fp_bag), entity-id
derivation, registry append, bijection invariants.
"""
import gzip
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "inbox"
META = ROOT / "data" / "meta"

FIX = json.loads((ROOT / "spec" / "fixtures" / "golden_v1.json").read_text())
BY_FILE = {f["file"].split("/")[-1]: f["expected"] for f in FIX["fixtures"]}


def row(platform, ids, name, fp, engagement=None, **extra):
    e = {"platform": platform, "ids": ids, "name": name, "fp_bag": fp and fp["fp_bag"],
         "node_count": fp and fp["node_count"], "node_types": fp and fp["node_types"],
         "engagement": engagement or {}, "updated_at": "2026-09-07T00:00:00+00:00"}
    e.update(extra)
    return e


def write(path, header, rows):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps(header, separators=(",", ":")) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")


def main():
    INBOX.mkdir(parents=True, exist_ok=True)
    for p in INBOX.glob("*"):
        p.unlink()
    for p in META.glob("*"):
        p.unlink()

    sd35 = BY_FILE["sd3.5_simple_example.json"]      # == flux_schnell
    flux = BY_FILE["flux_schnell.json"]
    starter = BY_FILE["gsc_starter_1.json"]          # == 01_get_started...
    hunyuan = BY_FILE["04_hunyuan_3d_2.1_subgraphed.json"]
    rh_export = BY_FILE["workflow.runninghub.export.har (entry 0, base64 body)"]
    empty = BY_FILE["empty_bag.json"]

    comfy_rows = [
        row("comfy_github", {"comfy_github": "sd3.5_simple_example"}, "SD3.5 Simple", sd35,
            {"gallery_views": 1000, "log_score": 5.0}),
        row("comfy_gallery", {"comfy_gallery": "flux-schnell-abc"}, "Flux Schnell", flux,
            {"cloud_runs": 500, "log_score": 4.2}),
        # starter collision pair -> distinct-types guard (10 types >= 8 so it
        # MERGES unless node_count differs; give differing node counts to
        # exercise the ±2 guard -> review queue)
        row("comfy_github", {"comfy_github": "gsc_starter_1"}, "GSC Starter 1",
            {**starter, "node_count": 10}, {"log_score": 2.0}),
        row("comfy_gallery", {"comfy_gallery": "get-started-xyz"}, "Get Started",
            {**starter, "node_count": 15}, {"log_score": 3.0}),
        row("comfy_github", {"comfy_github": "04_hunyuan_3d_2.1_subgraphed"}, "Hunyuan 3D subgraphed", hunyuan,
            {"log_score": 6.1}),
        row("comfy_gallery", {"comfy_gallery": "note-only"}, "Note Only (no fp)", empty, {}),
    ]
    rh_rows = [
        # CROSS-PLATFORM merge: same fp_bag as sd3.5/flux cluster
        row("runninghub", {"runninghub": "1975727985686917122"}, "RH starter-like", sd35,
            {"use_count": 80987, "log_score": 13.9}, source_domain="both", ready="ready_to_run",
            model_status="rh_hosted_verified", url="https://www.runninghub.ai/u/1975727985686917122"),
        row("runninghub", {"runninghub": "1975727985686919999"}, "RH hunyuan-like", hunyuan,
            {"use_count": 500, "log_score": 8.0}, source_domain="cn", ready="uncertain",
            model_status="bring_your_own"),
    ]
    write(INBOX / "comfy.jsonl.gz",
          {"header": True, "emitted_at": "2026-09-07T00:00:00+00:00", "vendor_sha": "fake-comfy-sha", "fp_spec": 1, "row_count": len(comfy_rows)},
          comfy_rows)
    write(INBOX / "rh.jsonl.gz",
          {"header": True, "emitted_at": "2026-09-07T00:00:00+00:00", "vendor_sha": "fake-rh-sha", "fp_spec": 1, "row_count": len(rh_rows)},
          rh_rows)

    r = subprocess.run([sys.executable, str(ROOT / "join" / "build_meta_index.py")], capture_output=True, text=True)
    print(r.stdout[-2500:] if r.stdout else r.stderr[-2500:])
    assert r.returncode == 0, "joiner crashed"

    stats = json.loads((META / "stats.json").read_text())
    print(f"\nSMOKE: rows_in={stats['rows_in']} entities={stats['entities']} "
          f"merged={stats['merged_entities']} review={len(stats['review_queue'])} "
          f"dup_groups={stats['duplicate_groups']} related_edges={stats['related_edges']}")

    meta = [json.loads(l) for l in (META / "meta_index.jsonl").read_text().splitlines() if l.strip()]
    by_fp = {m["fingerprint"]["fp_bag"]: m for m in meta}

    # LOW-ENTROPY collision (sd3.5/flux, 6 distinct types < 8) -> review queue,
    # NOT auto-merged (the guard doing its job — boilerplate starters)
    sd35_cluster = by_fp[sd35["fp_bag"]]
    assert sd35_cluster["status"] != "merged", "low-entropy cluster must not auto-merge"
    assert sd35["fp_bag"] in {q["fp_bag"] for q in stats["review_queue"]}

    # HIGH-ENTROPY cross-platform merge (hunyuan: 10 distinct types, comfy+RH)
    cross = by_fp[hunyuan["fp_bag"]]
    print(f"CROSS-PLATFORM cluster: {cross['entity_id']} status={cross['status']} "
          f"platforms={sorted(cross['platforms'])} cross_log_score={cross['cross_log_score']}")
    assert cross["status"] == "merged", "hunyuan cross-platform cluster should merge"
    assert set(cross["platforms"]) == {"comfy_github", "runninghub"}
    assert abs(cross["cross_log_score"] - 14.1) < 1e-6, cross["cross_log_score"]  # 6.1+8.0

    review_fps = {q["fp_bag"] for q in stats["review_queue"]}
    assert sd35["fp_bag"] in review_fps, "low-entropy collision pair should land in review queue"
    starter_in_review = starter["fp_bag"] in review_fps
    # starter pair has SAME node_count (10) and 10 distinct types -> it actually
    # auto-merges under v1 guards unless node_count differs; the smoke fixture
    # gave them 10 vs 15 to exercise the ±2 guard. Assert the guard fired:
    assert starter_in_review, "starter pair with node_count diff 5 should land in review queue"
    note_only = [m for m in meta if m["fingerprint"]["fp_bag"] is None]
    assert len(note_only) == 1, "empty-bag row becomes its own entity"

    v = subprocess.run([sys.executable, str(ROOT / "join" / "verify.py")], capture_output=True, text=True)
    print("VERIFY:", v.stdout.strip())
    assert v.returncode == 0, "verify failed"

    # cleanup: inbox test artifacts + join outputs (v0 ships empty)
    for p in INBOX.glob("*"):
        p.unlink()
    for p in META.glob("*"):
        p.unlink()
    print("\nSMOKE PASS — artifacts cleaned (repo ships in v0 state)")


if __name__ == "__main__":
    main()
