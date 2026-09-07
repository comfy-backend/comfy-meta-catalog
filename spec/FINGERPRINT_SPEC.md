# FINGERPRINT_SPEC v1

> THE LAW for content fingerprints. One implementation exists:
> `join/fingerprint.py` (vendored verbatim into both parent pipelines).
> A change here = bump `FP_SPEC`, regenerate `spec/fixtures/`, both sides
> re-emit, the join refuses `fp_spec ≠ supported`. Never fork this logic.

## Canonical text

**fp_bag computation (v1).** Input: one workflow JSON object.

**1. Collect.** `bag` = empty multiset of node-type strings. Walk
top-level `nodes[]`; for each node read `t = node["type"] or
node["class_type"]` (string, non-empty, **verbatim** — case-sensitive, no
aliasing, no whitespace changes). If `t ∈ DROP = {MarkdownNote, Note,
Reroute, PrimitiveNode, GetNode, SetNode}`: skip. If `t` is a subgraph
reference (key of `SUBGRAPHS`): resolve (below). Else `bag[t] += 1`.

**SUBGRAPHS** = `{s.id: s for s in workflow.definitions.subgraphs}` if
present, else `{}`.

**Resolving reference `r`:** for each node in `SUBGRAPHS[r].nodes[]` with
type `t`: DROP → skip; subgraph reference → resolve recursively (cycle
guard: each subgraph id may appear at most once per reference chain;
dangling reference → skip and increment the `dangling_refs` diagnostic);
else `bag[t] += 1`. **Each reference contributes the referenced subgraph's
bag exactly once** (referenced twice → twice; a defined-but-unreferenced
subgraph contributes **zero** — never add `definitions` wholesale in
addition to substitution). Ignore `inputNode`/`outputNode`.

API-format input (no `nodes`, top-level `{id: {class_type}}`): collect
`class_type` identically (no subgraphs in this format).

Everything else — id, pos, size, order, mode (muted nodes count),
widgets_values, title, flags, properties, groups, links, config, extra,
version, revision — is ignored. Empty `bag` → `fp_bag = NULL` (row still
emitted).

**2. Serialize.** `entries = [f"{t}:{n}" for (t, n) in bag.items()]`,
sorted by Unicode codepoint order of `t` (Python `sorted(bag.items())`);
`n` = decimal, unpadded, unsigned. `payload = ("\n".join(entries))
.encode("utf-8")` — LF separator (0x0A), **no trailing newline**, no BOM.
Emitters MUST hard-error on any type name containing U+000A (guarantees
injectivity — note: `:` legitimately occurs inside real type names, e.g.
`LayerUtility: PurgeVRAM V2`).

**3. Hash.** `fp_bag = "sha256:" + sha256(payload).hexdigest()` (lowercase
hex). `node_count = sum(bag.values())` (**not** raw `len(nodes)`, **not**
any existing analyzer column). `fp_spec = 1`.

**Implementation rule.** ONE implementation (`join/fingerprint.py`),
vendored verbatim into both pipelines (no re-implementation, no SQL
variant without an invariant gate). Parity = golden fixtures: ≥20
workflows with pinned expected `fp_bag` hex in `spec/fixtures/`, run in
both vendors' CI. Spec bump = bump version in spec + implementation +
regenerate goldens; both sides re-emit; the join refuses `fp_spec ≠
supported`.

## Empirical calibration (2026-09-07, whole comfy corpus)

- 626 graphs → 557 distinct bags; 56 duplicate groups / 125 files (20%)
  — e.g. `sd3.5_simple_example` ≡ `flux_schnell` (different models, same
  post-normalization bag); a 5-member starter group at ~5 distinct types.
- 254/626 (40.6%) carry `definitions.subgraphs`; 429 UUID-typed top
  nodes; 99 in-subgraph refs; no dangling refs, cycles, nested defs,
  unreferenced defs, or multi-instantiation observed (guards still
  specified).
- Drop-type prevalence: MarkdownNote 698, Note 102, Reroute 97,
  PrimitiveNode 72, GetNode 128.
- Median 9 distinct types / mean 11.7; mean 20.3 surviving nodes.
- One real RunningHub export (base64 body from the HAR capture): UI
  format, 35 nodes / 27 distinct types, no `definitions` key.

**Status: v1 is NOT frozen until the RH 1k-sample duplicate-rate
pre-study runs** (DESIGN_meta_catalog §8.1) — boilerplate starter
workflows at 104k scale will collide en masse; the join guards
(node_count ±2, cluster ≤ 4, distinct types ≥ 8, review queue) are
calibrated by that study.
