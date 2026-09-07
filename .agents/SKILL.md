# Agent Skill: comfy-meta-catalog — Session Know-How

> Seeded 2026-09-07 (session #9). The generalizable, recurring reference
> for agents working in THIS repo. For the parents' own know-how see
> beulahkemp/RH-workflow `.agents/SKILL.md` (pipeline) and
> trinitylivy/comfy-templates `.agents/SKILL.md` (web app + waves).

## 0. What this repo is (one paragraph)

A public, compute-only "runner-pattern" repo (same architecture as
comfy-backend/RH-workflow-runner: GHA does the work, private parents are
PAT-checked-out, secrets auto-redact from public logs). It joins two
private ComfyUI-workflow catalogs into one cross-platform index via
**content fingerprints**. It owns NO crawlers; each parent publishes an
interchange artifact (`interchange.jsonl.gz`) and this repo joins them.
The join is stdlib-only Python, deterministic, ~1 min at full scale.

## 1. The law files (never fork them)

- `spec/FINGERPRINT_SPEC.md` is the single source of truth for the
  fingerprint; `join/fingerprint.py` is THE implementation and is
  **vendored verbatim into both parents**. Never write a second
  implementation (no SQL variant, no JS port) without a golden-fixture
  invariant gate. A spec change = bump FP_SPEC everywhere + regenerate
  `spec/fixtures/golden_v1.json` + both sides re-emit; the join refuses
  mismatched fp_spec.
- `spec/INTERCHANGE_SPEC.md` + `spec/PLATFORM_REGISTRY.md` define the
  artifact contract. Enums are pinned — drift is a hard join failure.

## 2. Hard-won facts (from the 2026-09-07 review round)

- **Bag-collisions are real, not hypothetical**: 20% of the comfy corpus
  (56 groups / 125 files) shares a post-normalization bag — e.g.
  `sd3.5_simple_example` ≡ `flux_schnell` (different models!). That is
  why auto-merge requires ALL guards (same fp_bag AND |node_count diff|
  ≤ 2 AND cluster ≤ 4 AND distinct types ≥ 8) and everything else lands
  in the review queue. **v1 spec freeze is blocked on the RH 1k-sample
  duplicate-rate pre-study.**
- **Subgraph resolution is 40% of comfy**: 254/626 files carry
  `definitions.subgraphs`; UUID-typed top-level nodes must substitute the
  referenced subgraph's bag (recursive, cycle-guarded). RH's current
  `workflow_node` table has NO subgraph rows and stores UUID references
  as bogus node types — that is why fp_bag must be computed from the raw
  export JSON inside the analyzer (RH v8), not from a SQL pass.
- **The Jaccard-0.8 "verification tier" trap**: computing Jaccard
  WITHIN an fp_bag cluster is vacuous (identical bags ⇒ Jaccard ≡ 1.0).
  Jaccard's real job is CROSS-cluster related-edges.
- **Entity ids must never renumber**: `mw_ + sha256("v1|" + platform +
  "|" + id)[:16]`, derived from the cluster's smallest
  (registry-ordinal, platform-id); state lives in the append-only
  `data/meta/entity_registry.jsonl` (revisions append; update-in-place
  forbidden).
- **Per-row entity assignment bug** (caught by smoke): merged-cluster
  members share ONE entity (cluster-level min primary id), never
  per-row ids. `scripts/smoke_join.py` asserts this — keep it in CI.
- **Cadence reality**: RH refreshes daily 09:00 UTC; comfy's GHA weekly
  refresh is DORMANT (its sandbox Thursday 09:00 PT daemon is the real
  one) → the join schedule is Friday 09:00 UTC. Staleness > 8 days =
  hard fail + issue.
- **v0 has no submodules by design**: private-repo URLs in a public
  `.gitmodules` leak vendor existence; provenance rides in each
  artifact's header (`vendor_sha`). Submodules return only if the v2 UI
  needs vendor code.

## 3. Operating

- Self-test on push (join.yml): syntax + verify + smoke; the real join
  step exits cleanly at v0 (no artifacts). Enable the schedule block at
  v1.
- `scripts/fetch_artifacts.sh` needs `GH_PAT` (reads both private
  parents). It tolerates missing emitters — the joiner decides if
  that's fatal.
- The smoke test cleans up after itself (repo ships in v0 state — empty
  data/inbox, empty data/meta).
- Corpus-dependent fixture checks skip silently when the comfy corpus
  is absent (CI); the vendor-side CI runs cover them there. Golden
  fixtures whose source file is missing are skipped, not failed.

## 4. Session protocol

Same as the parents: PLAN-style tracking lives in the RH repo (this
repo's roadmap section in its README is the mirror); every session:
read this file, do the work, push (git is the disk), never force-push,
append the worklog entry in the RH repo's WORKLOG.md, and update this
file with anything that bites.
