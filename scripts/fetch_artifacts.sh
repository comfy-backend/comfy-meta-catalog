# fetch_artifacts.sh — pull the two interchange artifacts into data/inbox/.
# Used by join.yml (CI) and manually. Tolerates absence at v0 (vendors
# have not emitted yet) — the joiner itself decides whether that's fatal.
#
# Auth: GH_PAT env var (repo-scoped; both vendor repos are readable by it).
# RH artifact:  beulahkemp/RH-workflow-data      :: snapshots/interchange.jsonl.gz
# comfy artifact: trinitylivy/comfy-templates    :: work/comfy-templates/data/unified/interchange.jsonl.gz
set -euo pipefail

PAT="${GH_PAT:?GH_PAT env var required}"
INBOX="$(dirname "$0")/../data/inbox"
mkdir -p "$INBOX"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- RH-workflow-data (private; blobless partial clone, no LFS smudge)
if git clone --filter=blob:none --no-checkout --depth 1 \
     "https://${PAT}@github.com/beulahkemp/RH-workflow-data.git" "$TMP/rhdata" 2>/dev/null; then
  if git -C "$TMP/rhdata" cat-file -e HEAD:snapshots/interchange.jsonl.gz 2>/dev/null; then
    git -C "$TMP/rhdata" show HEAD:snapshots/interchange.jsonl.gz > "$INBOX/rh.jsonl.gz"
    echo "fetched RH interchange -> data/inbox/rh.jsonl.gz"
  else
    echo "NOTE: RH-workflow-data has no snapshots/interchange.jsonl.gz yet (v0 — emitter pending)"
  fi
else
  echo "NOTE: RH-workflow-data clone failed (network/auth?)"
fi

# --- comfy-templates (private; depth-1)
if git clone --depth 1 "https://${PAT}@github.com/trinitylivy/comfy-templates.git" \
     "$TMP/comfy" 2>/dev/null; then
  SRC="$TMP/comfy/work/comfy-templates/data/unified/interchange.jsonl.gz"
  if [ -f "$SRC" ]; then
    cp "$SRC" "$INBOX/comfy.jsonl.gz"
    echo "fetched comfy interchange -> data/inbox/comfy.jsonl.gz"
  else
    echo "NOTE: comfy-templates has no unified/interchange.jsonl.gz yet (v0 — emitter pending)"
  fi
else
  echo "NOTE: comfy-templates clone failed (network/auth?)"
fi

ls -la "$INBOX" || true
