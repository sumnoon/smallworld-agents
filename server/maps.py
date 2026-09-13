"""Shared map geometry used by validation, navigation and save upgrades."""
import copy
import json
from pathlib import Path

LANDMARK_ASSETS = {"market-pavilion","garden-conservatory","plaza-fountain","blossom-tree"}


def obstacle_cells(layout):
    cells = {(x,y) for b in layout["buildings"] for x in range(b["x"]-2,b["x"]+2) for y in range(b["y"]-2,b["y"]+2)}
    cells.update((p["x"],p["y"]) for p in layout["props"])
    for o in layout.get("landmarks",[]):
        x0,y0,x1,y1 = o["footprint"]
        cells.update((x,y) for x in range(x0,x1+1) for y in range(y0,y1+1))
    cells.update((x,y) for y,row in enumerate(layout.get("terrain",[])) for x,tile in enumerate(row) if tile==12)
    return cells


def upgrade_classic(layout):
    """Only extend the unchanged original map; preserve custom scenarios."""
    folder = Path(__file__).resolve().parents[1]/"scenarios"
    classic = json.loads((folder/"classic-neighborhood.json").read_text(encoding="utf-8"))
    if layout.get("size") != 16 or any(layout.get(k) != classic[k] for k in ("buildings","props","places")) or layout.get("terrain") or layout.get("landmarks"):
        return layout, False
    expanded = json.loads((folder/"neighborhood.json").read_text(encoding="utf-8"))
    result = {**copy.deepcopy(layout),**expanded,"residents":copy.deepcopy(layout["residents"])}
    defaults = {p["id"]:p for p in expanded["residents"]}
    originals = {p["id"]:p for p in classic["residents"]}
    for p in result["residents"]:
        if p["id"] in originals and p["plan"] == originals[p["id"]]["plan"]:
            p["plan"] = copy.deepcopy(defaults[p["id"]]["plan"])
    return result, True
