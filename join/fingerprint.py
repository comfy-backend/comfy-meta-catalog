"""The canonical FINGERPRINT_SPEC v1 implementation.

THIS FILE IS THE LAW. `spec/FINGERPRINT_SPEC.md` defines the rules; this
module implements them. It is vendored VERBATIM into both parent pipelines
(comfy-templates `07_derive_web_extras` and RH-workflow `rh_catalog/analyze`
v8) — no re-implementation, no SQL variant without an invariant gate.

Parity is enforced by golden fixtures (`spec/fixtures/`, run by both
vendors' CI and by join/verify.py).

Stdlib only (both parents must run it without dependencies).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

FP_SPEC = 1

# Types dropped before hashing: documentation noise + pure plumbing.
DROP = {"MarkdownNote", "Note", "Reroute", "PrimitiveNode", "GetNode", "SetNode"}


class FingerprintError(ValueError):
    """Raised on spec-violating input (e.g. injectivity guard)."""


def compute_fp(workflow: Any) -> dict:
    """Compute the bag-of-nodes fingerprint of one workflow JSON object.

    Returns:
        {
          "fp_spec": 1,
          "fp_bag": "sha256:..." | None,   # None = empty bag after drops
          "node_count": int,               # sum of bag values (NOT len(nodes))
          "node_types": sorted list of distinct surviving types,
          "dangling_refs": int,            # subgraph refs with no definition
          "cycle_guards": int,             # cyclic subgraph references skipped
        }
    """
    if not isinstance(workflow, dict):
        raise FingerprintError("workflow must be a JSON object")

    subs = _subgraphs(workflow)
    bag: dict[str, int] = {}
    diag = {"dangling_refs": 0, "cycle_guards": 0}

    nodes = workflow.get("nodes")
    if isinstance(nodes, list):
        # UI-export format
        for node in nodes:
            if isinstance(node, dict):
                _collect(node, bag, subs, diag, chain=())
    elif nodes is None:
        # API format: top-level {id: {class_type: ...}} — no subgraphs exist
        # in this format.
        for spec in workflow.values():
            if isinstance(spec, dict) and isinstance(spec.get("class_type"), str):
                _add(spec["class_type"], bag)

    payload_hash = _hash(bag)
    return {
        "fp_spec": FP_SPEC,
        "fp_bag": payload_hash,
        "node_count": sum(bag.values()),
        "node_types": sorted(bag),
        **diag,
    }


def fp_bag_of(workflow: Any) -> str | None:
    """Convenience: just the hash (None for empty bags)."""
    return compute_fp(workflow)["fp_bag"]


# ---------------------------------------------------------------- internals


def _subgraphs(workflow: dict) -> dict:
    defs = workflow.get("definitions")
    if not isinstance(defs, dict):
        return {}
    subs = defs.get("subgraphs")
    if not isinstance(subs, list):
        return {}
    out = {}
    for s in subs:
        if isinstance(s, dict) and isinstance(s.get("id"), str):
            out[s["id"]] = s
    return out


def _collect(node: dict, bag: dict, subs: dict, diag: dict, chain: tuple) -> None:
    t = node.get("type")
    if not isinstance(t, str) or not t:
        t = node.get("class_type")
        if not isinstance(t, str) or not t:
            return
    if "\n" in t:
        # Spec injectivity guard: a type name containing U+000A could
        # collide with the serialization separator. Emitters MUST
        # hard-error; we raise the same class for symmetry.
        raise FingerprintError(f"type name contains U+000A: {t[:60]!r}")
    if t in DROP:
        return
    if t in subs:
        # Subgraph reference: contribute the referenced subgraph's bag
        # exactly once per reference (referenced twice -> twice).
        if t in chain:
            diag["cycle_guards"] += 1
            return
        sub_nodes = subs[t].get("nodes")
        if isinstance(sub_nodes, list):
            for sn in sub_nodes:
                if isinstance(sn, dict):
                    _collect(sn, bag, subs, diag, chain + (t,))
        return
    # Plain node type. (A type name that is NOT a subgraph key but looks
    # like a UUID is counted verbatim — the spec counts what exists.)
    bag[t] = bag.get(t, 0) + 1


def _add(t: str, bag: dict) -> None:
    if "\n" in t:
        raise FingerprintError(f"type name contains U+000A: {t[:60]!r}")
    if t in DROP:
        return
    bag[t] = bag.get(t, 0) + 1


def _hash(bag: dict) -> str | None:
    if not bag:
        return None
    entries = [f"{t}:{n}" for t, n in sorted(bag.items())]
    payload = ("\n".join(entries)).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def compute_fp_file(path: str) -> dict:
    """Read one workflow JSON file and fingerprint it."""
    with open(path, "rb") as f:
        workflow = json.loads(f.read().decode("utf-8"))
    return compute_fp(workflow)
