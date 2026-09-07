# comfy-meta-catalog

**The meta cross-platform ComfyUI workflow catalog** — joins the two
ComfyUI-workflow catalogs into one browsable, analyzable index:

| parent | what it brings | scale |
|---|---|---|
| [trinitylivy/comfy-templates](https://github.com/trinitylivy/comfy-templates) (private) | official templates: comfy.org gallery + Comfy-Org/workflow_templates GitHub; real multi-source engagement (cloud_runs, gallery_views, search_rank) — the **quality anchor** | 860 |
| [beulahkemp/RH-workflow](https://github.com/beulahkemp/RH-workflow) (private) | RunningHub (.ai + .cn) workflows with deep per-workflow analysis (nodes, packs, models, readiness) — the **coverage + depth anchor** | 104,187 |

The core value: **cross-platform identity + cross-platform quality
ranking** — a workflow popular on both platforms ranks above one popular
on either alone (`cross_log_score`); an RH workflow structurally identical
to an official template inherits a curated-quality signal. Per-platform
signals are always preserved raw, never replaced (comfy-templates'
cardinal rule).

## Status: v0 (seeded 2026-09-07)

- ✅ `spec/FINGERPRINT_SPEC.md` — the canonical content-fingerprint law
  (byte-level; one implementation: `join/fingerprint.py`)
- ✅ `spec/INTERCHANGE_SPEC.md` + `spec/PLATFORM_REGISTRY.md` — the JSONL
  contract each parent catalog publishes
- ✅ `join/fingerprint.py` — THE implementation (stdlib-only, vendored
  into both parents)
- ✅ `spec/fixtures/golden_v1.json` — 27 golden fixtures from the REAL
  corpora (comfy samples, a real RunningHub export from the HAR capture,
  5 synthetic edge cases) including the known collision pair
  (`sd3.5_simple_example` ≡ `flux_schnell`)
- ✅ `join/build_meta_index.py` — the joiner: fp-bag clustering with
  guards (node_count ±2 · cluster ≤ 4 · distinct types ≥ 8 · review
  queue), hash-based stable entity ids + append-only registry,
  cross-cluster Jaccard related-edges, loud collision report
- ✅ `join/verify.py` — fixtures parity + join invariants (bijection,
  registry replay, cross_log_score recompute)
- ✅ `.github/workflows/join.yml` — self-test gate on push; Friday
  09:00 UTC schedule + artifact-age drift alerts (ENABLE AT v1)
- ⬜ v1: both parents emit `interchange.jsonl.gz` (RH: quality +
  fingerprint work first — see RH `docs/DESIGN_cross_pollination.md`)
- ⬜ v2: the meta UI (generalized from the comfy-templates web app
  skeleton); owner sign-off before publishing overlap analysis
- ⬜ v3: more platform adapters (OpenArt, Civitai, …) — each is one new
  interchange emitter

**Empirical calibration baked into the seed**: the comfy corpus measures
a **20% bag-duplicate rate** (56 groups / 125 files — boilerplate
starters collide by construction), which is why merging is guarded and
low-entropy clusters land in a review queue instead. FINGERPRINT_SPEC v1
is NOT frozen until the RH 1k-sample duplicate-rate pre-study runs.

## Layout

```
spec/            the law: FINGERPRINT_SPEC / INTERCHANGE_SPEC / PLATFORM_REGISTRY / fixtures/
join/            fingerprint.py (THE impl) · build_meta_index.py · verify.py
scripts/         gen_fixtures.py · smoke_join.py · fetch_artifacts.sh
data/inbox/      vendor interchange artifacts land here (fetched by CI)
data/meta/       output: meta_index.jsonl · entity_registry.jsonl · related_network.jsonl · stats.json
```

## Design docs

The founding design (entity model, merge guards, evolution path) lives in
the RH-workflow repo: `docs/DESIGN_meta_catalog.md` (v2, review-hardened)
with its companion `docs/DESIGN_cross_pollination.md`. This repo carries
the executable specs.

## Running locally

```bash
python3 join/verify.py            # fixtures parity + invariants (v0 soft-pass)
python3 scripts/smoke_join.py     # end-to-end joiner smoke on real fixture fps
GH_PAT=… bash scripts/fetch_artifacts.sh
python3 join/build_meta_index.py  # the real join (needs artifacts in data/inbox/)
```

## Conventions (inherited from both parents)

- **GIT IS THE DISK** — push every meaningful unit; the registry and
  join outputs are committed state.
- **Stdlib-only Python** for the join (no dependency drift between
  vendors).
- **Missing-driven**: no artifacts → loud, filed issue, never silent.
- **Never force-push.** Output commits are scoped to `data/meta/` only.
