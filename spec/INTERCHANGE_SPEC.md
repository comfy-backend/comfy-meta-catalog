# INTERCHANGE_SPEC v1

The JSONL contract each parent catalog publishes for the meta joiner.

## Container

- ONE gzipped JSONL file per catalog, **weekly** (the join is weekly —
  daily artifacts would be unread 6 of 7 days), sorted by primary id for
  diffability.
- Encoding: UTF-8, `ensure_ascii=False`, `separators=(",", ":")`, one row
  per line, trailing newline at EOF.
- **Line 1 is a header row**:
  `{"header":true,"emitted_at":"<ISO-8601>","vendor_sha":"<catalog repo SHA at emit time>","fp_spec":1,"row_count":N}`
  — `vendor_sha` is the provenance pin (v0 has no submodules by design).
- RH location: `RH-workflow-data: snapshots/interchange.jsonl.gz`
  (written by the snapshot phase; rides the existing data-repo sync).
  Comfy location: `trinitylivy/comfy-templates:
  work/comfy-templates/data/unified/interchange.jsonl.gz` (written by
  `07_derive_web_extras`).

## Row schema

```jsonc
{
  "platform": "runninghub",            // PLATFORM_REGISTRY key
  "ids": { ... },                      // platform-specific id map, see below
  "name": "...",                       // primary display name
  "fp_bag": "sha256:...",              // FINGERPRINT_SPEC v1; null when no graph
  "node_count": 23,                    // spec node_count (sum of bag values)
  "node_types": ["..."],               // sorted distinct surviving types
  "engagement": {
    // raw per-platform signals, preserved verbatim, never replaced.
    // NULL = unknown, never 0.
    "use_count": 80987, "like_count": 2200, "collect_count": 441,
    "log_score": 13.9, "log_score_adj": 12.31, "publish_time": "..."
  },
  "source_domain": "both",             // RH only; enum: ai|cn|both
  "ready": "ready_to_run",             // enum: ready_to_run|not_ready|uncertain
  "model_status": "rh_hosted_verified",// enum: bring_your_own|no_models|
                                        //       rh_hosted_likely|rh_hosted_verified
  "url": "...", "download_url": "...",
  "updated_at": "..."                  // row-level emit version
}
```

### `ids` shapes

- **comfy rows** (one per `unified_index.json` entry): carry BOTH real
  source ids where present:
  `{"comfy_gallery": "<shareId>", "comfy_github": "<template name>"}`
  (either may be absent — gallery-only / github-only rows).
- **RH rows**: `{"runninghub": "<19-digit numeric id>"}`
  (the id space is shared across .ai/.cn — `source_domain` carries the
  domain attribution; regional variants fold into ONE row).

### Optional facet files (same keying, separate files)

- `models.jsonl`: `{platform, ids, models: [model ref strings]}`
- `tags.jsonl`: `{platform, ids, tags: [tag strings]}`

Both sides emit them when the facet data exists (RH: workflow_model +
workflow_tag; comfy: unified `models[]` + unioned `tags[]`). They feed
cross-platform model/tag overlap analytics (v3); the joiner tolerates
their absence.

## Enum pins (drift = hard join failure)

| field | allowed values |
|---|---|
| `platform` | registry keys only (`comfy_gallery`, `comfy_github`, `runninghub`, `rh_app`) |
| `source_domain` | `ai` \| `cn` \| `both` |
| `ready` | `ready_to_run` \| `not_ready` \| `uncertain` (maps RH's 1/0/-1) |
| `model_status` | `bring_your_own` \| `no_models` \| `rh_hosted_likely` \| `rh_hosted_verified` |

## Coverage notes

- comfy: ~833/860 rows fingerprinted (gallery-only rows have no local
  graph → fp_bag null; 07's `_load_graph` resolves GitHub-only graphs via
  its runtime cache; the emitter skips `_download_report.json`).
- RH: all rows with an export file; the remainder (persistent 401/404
  export failures, ~0.05%) emit fp_bag null.
- Size reality: ~0.9-1.1 KB/row at RH name lengths → ~95-115 MB raw /
  ~20 MB gz for 104k rows; ~660 KB gz for comfy's 860.
