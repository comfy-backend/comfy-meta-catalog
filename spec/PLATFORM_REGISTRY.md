# PLATFORM_REGISTRY v1

The authoritative list of entity platforms. Adding a platform = new
registry row + an interchange emitter in that platform's pipeline. The
ordinal defines entity-id derivation order (smallest wins).

| key | id shape | ordinal | cardinality (2026-09-07) | notes |
|---|---|---|---|---|
| `comfy_gallery` | shareId (hex string) | 1 | 626 members | comfy.org gallery source |
| `comfy_github` | template name (string) | 2 | 616 members | Comfy-Org/workflow_templates; union rows w/ gallery |
| `runninghub` | workflow_id (19-digit numeric string, shared .ai/.cn space) | 3 | 104,187 members | domain attribution via `source_domain` |
| `rh_app` | app id (string) | 4 | 114,717 wrappers | LINKED, never merged (productized wrappers are distinct artifacts) |

**cloud.comfy.org is NOT an entity platform**: its template index is
byte-identical to Comfy-Org/workflow_templates (same sha256) — joining it
would double-count. It remains an auxiliary-asset source inside
comfy-templates (node maps, model catalog, extensions).

Rules:
- Platform keys are frozen once published (consumers key on them).
- `rh_app` rows link to entities via their backing `workflow_id`; they
  never participate in fingerprint merging.
- The ordinal is stable; new platforms append at the end.
