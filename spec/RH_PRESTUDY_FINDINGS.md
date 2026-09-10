# RH 1k-Sample Bag-Duplicate Pre-Study — FINDINGS (T4 item 4)

**Date:** 2026-09-10 (session #10)
**Data:** `RH-workflow-data` @ `dd62b8209fdb5f373f47773e1cc4b9df15d4b0fe` (104,217 export files)
**Method:** uniform random sample, seed 42, N=1000, THE canonical `join/fingerprint.py`
(FP_SPEC=1). Raw report: `data/rh_prestudy_1k.json`. Script:
`scripts/rh_prestudy.py` (reproducible: seed + HEAD embedded).

## Headline numbers

| Metric | Value |
|---|---|
| Fingerprinted | 1000/1000 (0 parse errors) |
| Distinct bags | 945 |
| Rows sharing a bag with ≥1 other | **87 (8.7%)** |
| Collision clusters | 34 (22 pairs, 8 triples, 1 quad, 3 quintuples) |
| Empty bags (`fp_bag: null`) | 2 |
| Subgraph machinery exercised | **0** dangling refs, 0 cycle guards |
| node_count median / p90 | 26 / 63 |

## Comparison with the comfy corpus (session #9)

comfy measured a **20%** bag-collision rate; RH measures **8.7%** — roughly
half, but the same order of magnitude. Both corpora confirm the founding
premise of the guarded joiner: **bag identity alone is NOT merge-safe on
either platform.** Un-guarded bag-equality joining would produce false
entities at an 8-20% rate.

## Guard calibration implications (what this study was FOR)

1. **The collision mass sits in low-complexity workflows.** The largest RH
   clusters are 5–19 node / 4–17 distinct-type pipelines — the
   `LoadImage → RH_*TextToImage → SaveImage` family and friends. The
   existing merge guards (≥8 distinct types + entropy thresholds) route
   exactly this class to the review queue — the guard design is
   **validated on RH data**, not just comfy data.
2. **A same-platform cluster-size cap is warranted.** One RH cluster has 5
   members and another 17 distinct types — the current type-count guard
   alone would auto-merge a 3-5 member same-platform cluster. Within-platform
   same-bag multiplicity is a *re-publish* pattern, not a cross-platform
   identity signal. Recommendation (joiner v1 amendment): same-platform
   clusters with ≥3 members route to review even when they pass the entropy
   guard; cross-platform pairs keep the current rules.
3. **RH exports do not use subgraphs** (0 dangling refs, 0 cycle guards
   across 1000). Consistent with the earlier discovery that
   `workflow_node` has no subgraph rows. The subgraph-aware branch of the
   fingerprint spec remains exercised only by comfy corpora — parity there
   continues to ride on the comfy golden fixtures.
4. **Empty bags are real on RH too** (2/1000) — the `fp_bag: null` +
   NULL-signal discipline in INTERCHANGE_SPEC is not hypothetical.
5. **FINGERPRINT_SPEC v1 freeze: GO.** No RH-side evidence contradicts the
   spec; the measured duplicate rate (8.7%) is within the guard envelope
   the joiner was calibrated for (its guards were sized for the harsher
   20% comfy case).

## Operational notes

- Fetch path: blobless clone + per-blob lazy fetch measured ~0.9s/blob
  (one HTTPS round-trip per blob — 1000 files ≈ 15 min). The study instead
  fetches raw files from raw.githubusercontent.com with 12 concurrent
  workers (~49s wall for 1000 files). Lesson for future studies: materialize
  via the CDN, not the git promisor, when sampling.
- Era skew is inherent to uniform-over-files sampling: shards are by
  snowflake-prefix (17: 139 files, 18: 2,879, 19: 27,974, 20: 73,225), so
  ~70% of the sample is era-20 workflows. This matches the catalog's actual
  mass distribution — the right default for a corpus-level rate.
