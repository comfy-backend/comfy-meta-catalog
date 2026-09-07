#!/usr/bin/env python3
"""Generate spec/fixtures/golden_v1.json — real golden fixtures for
FINGERPRINT_SPEC v1, computed from the actual corpora:

- ~16 deterministic comfy corpus samples (every 31st file, sorted)
- the known collision pair (sd3.5_simple_example + flux_schnell) + a
  subgraphed file + starter-group members
- 1 real RunningHub export (base64 body from the HAR capture)
- 5 synthetic edge cases (subgraph refs, empty bag, API format, drops,
  double-reference)

Run from the meta repo root. Writes spec/fixtures/golden_v1.json and
spec/fixtures/synthetic/*.json.
"""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "join"))
from fingerprint import compute_fp  # noqa: E402

COMFY = Path("/home/z/rhw/comfy-templates/work/comfy-templates/data/raw/workflow_jsons")
HAR = Path("/home/z/rhw/code/workflow.runninghub.export.har")
OUT = Path("/home/z/rhw/meta/spec/fixtures/golden_v1.json")
SYN = Path("/home/z/rhw/meta/spec/fixtures/synthetic")


def comfy_files():
    files = sorted(p for p in COMFY.glob("*.json") if p.name != "_download_report.json")
    spread = files[::31][:16]
    named = [
        "sd3.5_simple_example.json",
        "flux_schnell.json",
        "04_hunyuan_3d_2.1_subgraphed.json",
        "gsc_starter_1.json",
        "01_get_started_text_to_image.json",
    ]
    seen = set()
    out = []
    for p in spread + [COMFY / n for n in named]:
        if p.exists() and p.name not in seen:
            seen.add(p.name)
            out.append(p)
    return out


def rh_export():
    har = json.loads(HAR.read_bytes().decode("utf-8"))
    entry = har["log"]["entries"][0]
    body = entry["response"]["content"]
    raw = base64.b64decode(body["text"]) if body.get("encoding") == "base64" else body["text"].encode()
    return json.loads(raw.decode("utf-8"))


SYNTHETIC = {
    "subgraph_reference.json": {
        "nodes": [
            {"id": 1, "type": "CheckpointLoaderSimple"},
            {"id": 2, "type": "e3a57dc6-b2bf-4d05-927d-3715b40d2a77"},
        ],
        "definitions": {
            "subgraphs": [
                {
                    "id": "e3a57dc6-b2bf-4d05-927d-3715b40d2a77",
                    "nodes": [
                        {"id": 10, "type": "CLIPTextEncode"},
                        {"id": 11, "type": "KSampler"},
                    ],
                }
            ]
        },
    },
    "empty_bag.json": {
        "nodes": [
            {"id": 1, "type": "MarkdownNote"},
            {"id": 2, "type": "Note"},
            {"id": 3, "type": "Reroute"},
            {"id": 4, "type": "PrimitiveNode"},
            {"id": 5, "type": "GetNode"},
            {"id": 6, "type": "SetNode"},
        ]
    },
    "api_format.json": {
        "3": {"class_type": "KSampler", "inputs": {}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
        "3-2": {"class_type": "KSampler", "inputs": {}},
    },
    "drop_and_plumbing.json": {
        "nodes": [
            {"id": 1, "type": "Note"},
            {"id": 2, "type": "GetNode"},
            {"id": 3, "type": "VAEDecode"},
            {"id": 4, "type": "VAEDecode"},
            {"id": 5, "type": "SaveImage", "mode": 4},
        ]
    },
    "double_reference.json": {
        "nodes": [
            {"id": 1, "type": "LoadImage"},
            {"id": 2, "type": "sub-a"},
            {"id": 3, "type": "sub-a"},
        ],
        "definitions": {
            "subgraphs": [
                {"id": "sub-a", "nodes": [{"id": 9, "type": "ImageScale"}]},
                {"id": "sub-unused", "nodes": [{"id": 8, "type": "NeverUsed"}]},
            ]
        },
    },
}


def main():
    fixtures = []

    for p in comfy_files():
        wf = json.loads(p.read_bytes().decode("utf-8"))
        r = compute_fp(wf)
        fixtures.append(
            {
                "source": "comfy_corpus",
                "file": f"trinitylivy/comfy-templates :: work/comfy-templates/data/raw/workflow_jsons/{p.name}",
                "expected": r,
            }
        )

    try:
        wf = rh_export()
        r = compute_fp(wf)
        fixtures.append(
            {
                "source": "rh_har_export",
                "file": "beulahkemp/RH-workflow :: har/workflow.runninghub.export.har (entry 0, base64 body)",
                "expected": r,
            }
        )
    except Exception as e:  # noqa: BLE001
        print(f"WARN: RH HAR export failed: {e}")

    SYN.mkdir(parents=True, exist_ok=True)
    for name, wf in SYNTHETIC.items():
        path = SYN / name
        path.write_text(json.dumps(wf, indent=1) + "\n", encoding="utf-8")
        r = compute_fp(wf)
        fixtures.append(
            {
                "source": "synthetic",
                "file": f"spec/fixtures/synthetic/{name}",
                "expected": r,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"fp_spec": 1, "fixture_count": len(fixtures), "fixtures": fixtures}, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(fixtures)} fixtures")
    for f in fixtures:
        print(f"  {f['file'].split('/')[-1]:50s} fp={f['expected']['fp_bag']} n={f['expected']['node_count']}")


if __name__ == "__main__":
    main()
