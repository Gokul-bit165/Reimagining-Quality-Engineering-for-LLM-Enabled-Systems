"""Print the defect-class x app coverage table from the manifests.

Run: python -m sandbox_apps._common.coverage_table
"""

from __future__ import annotations

from sandbox_apps._common.probe_utils import APPS, DEFECT_CLASSES, load_manifest


def coverage_matrix() -> dict[str, dict[str, list[str]]]:
    matrix: dict[str, dict[str, list[str]]] = {c: {a: [] for a in APPS} for c in DEFECT_CLASSES}
    for app in APPS:
        for entry in load_manifest(app)["defects"]:
            matrix[entry["class"]][app].append(entry["id"])
    return matrix


def render() -> str:
    matrix = coverage_matrix()
    rows = ["| defect class | " + " | ".join(APPS) + " |", "|---|" + "---|" * len(APPS)]
    for cls in DEFECT_CLASSES:
        cells = [", ".join(matrix[cls][a]) or "-" for a in APPS]
        rows.append(f"| {cls} | " + " | ".join(cells) + " |")
    totals = [str(len(load_manifest(a)["defects"])) for a in APPS]
    rows.append("| **total defects** | " + " | ".join(totals) + " |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(render())
