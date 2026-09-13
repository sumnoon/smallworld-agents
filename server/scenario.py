"""Portable scenario validation and original procedural town population."""
import copy
import re
from collections import deque
from .maps import obstacle_cells, LANDMARK_ASSETS

SKINS = ["maya", "noah", "elena", "samir", "jun"]


def validate(layout):
    layout = copy.deepcopy(layout)
    if type(layout) is not dict or type(layout.get("size")) is not int or not 12 <= layout["size"] <= 32:
        raise ValueError("Scenario size must be an integer from 12 to 32")
    n = layout["size"]
    def xy(p):
        if not isinstance(p,dict):
            raise ValueError("Scenario entries must be objects")
        if any(type(p.get(k)) is not int or not 0 <= p[k] < n for k in ("x", "y")):
            raise ValueError("Scenario coordinates must be integer tiles within the map")
    if not isinstance(layout.get("places"),dict) or not {"cafe", "shop", "park", "home", "studio"}.issubset(layout["places"]) or len(layout["places"]) > 20:
        raise ValueError("Scenario must contain cafe, shop, park, home and studio")
    if any(not isinstance(key,str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,30}",key) for key in layout["places"]):
        raise ValueError("Place IDs must be simple identifiers")
    for pos in layout["places"].values():
        if not isinstance(pos, list) or len(pos) != 2:
            raise ValueError("Place coordinates need [x,y]")
        xy(dict(zip(("x", "y"), pos)))
    if not isinstance(layout.get("buildings"), list) or len(layout["buildings"]) > 20:
        raise ValueError("At most 20 buildings are allowed")
    blocked = set()
    for b in layout["buildings"]:
        xy(b)
        if type(b.get("index")) is not int or not 0 <= b["index"] <= 3:
            raise ValueError("Building artwork index must be 0-3")
        blocked.update((x,y) for x in range(b["x"]-2,b["x"]+2) for y in range(b["y"]-2,b["y"]+2))
    if not isinstance(layout.get("props"), list) or len(layout["props"]) > 150:
        raise ValueError("At most 150 props are allowed")
    for p in layout["props"]:
        xy(p)
        if type(p.get("i")) is not int or not 0 <= p["i"] <= 15 or type(p.get("w")) not in (int,float) or not 10 <= p["w"] <= 150:
            raise ValueError("Invalid prop artwork or width")
        blocked.add((p["x"],p["y"]))
    terrain = layout.get("terrain")
    if terrain is not None and (not isinstance(terrain,list) or len(terrain)!=n or any(not isinstance(row,list) or len(row)!=n or any(type(t) is not int or not 0<=t<=15 for t in row) for row in terrain)):
        raise ValueError("Terrain must be a square grid of tile indices 0-15")
    landmarks = layout.get("landmarks",[])
    if not isinstance(landmarks,list) or len(landmarks)>80:
        raise ValueError("At most 80 landmarks are allowed")
    landmark_ids = set()
    for obj in landmarks:
        xy(obj)
        if not isinstance(obj.get("id"),str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,40}",obj["id"]) or obj["id"] in landmark_ids or obj.get("asset") not in LANDMARK_ASSETS:
            raise ValueError("Landmarks require a unique ID and known artwork")
        landmark_ids.add(obj["id"])
        bounds = obj.get("footprint")
        if not isinstance(bounds,list) or len(bounds)!=4 or any(type(v) is not int or not 0<=v<n for v in bounds) or bounds[0]>bounds[2] or bounds[1]>bounds[3] or (bounds[2]-bounds[0]+1)*(bounds[3]-bounds[1]+1)>16:
            raise ValueError("Landmark footprint must be a valid rectangle of at most 16 tiles")
        if type(obj.get("w")) not in (int,float) or not 20<=obj["w"]<=280 or type(obj.get("base_offset",0)) not in (int,float) or not 0<=obj.get("base_offset",0)<=60 or type(obj.get("blocks_view",False)) is not bool:
            raise ValueError("Invalid landmark dimensions or visibility")
    districts = layout.get("districts",[])
    if not isinstance(districts,list) or len(districts)>12:
        raise ValueError("At most 12 districts are allowed")
    for district in districts:
        if not isinstance(district,dict) or district.get("place") not in layout["places"] or not isinstance(district.get("name"),str) or not 1<=len(district["name"])<=80 or not isinstance(district.get("color"),str) or not re.fullmatch(r"#[0-9a-fA-F]{6}",district["color"]):
            raise ValueError("Invalid district destination, name or color")
    blocked = obstacle_cells(layout)
    if any(tuple(p) in blocked for p in layout["places"].values()):
        raise ValueError("Places must be on walkable ground")
    people = layout.get("residents")
    if not isinstance(people,list) or not 2 <= len(people) <= 26:
        raise ValueError("Choose 1-25 residents plus Alex")
    ids, positions = set(), set()
    for p in people:
        xy(p)
        if not isinstance(p.get("id"),str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,30}",p["id"]) or p["id"] in ids:
            raise ValueError("Resident IDs must be unique simple identifiers")
        ids.add(p["id"])
        pos = (p["x"],p["y"])
        if pos in positions or pos in blocked:
            raise ValueError("Residents must spawn on separate walkable tiles")
        positions.add(pos)
        for key in ("name","role","bio"):
            if not isinstance(p.get(key),str) or not 1 <= len(p[key]) <= 500:
                raise ValueError("Resident names, roles and biographies must be nonempty text")
        skin = p.get("skin",p["id"])
        if skin not in SKINS+["visitor"]:
            raise ValueError("Choose an existing character skin")
        p["skin"] = skin
        if not isinstance(p.get("plan"),list) or len(p["plan"]) > 12 or (p["id"] != "visitor" and not p["plan"]):
            raise ValueError("Residents need 1-12 daily activities")
        for step in p["plan"]:
            if not isinstance(step,dict) or step.get("place") not in layout["places"] or not isinstance(step.get("activity"),str) or not 1 <= len(step["activity"]) <= 150:
                raise ValueError("Invalid daily activity")
    if "visitor" not in ids:
        raise ValueError("Scenario requires the visitor player")
    start = tuple(layout["places"]["park"])
    reached, queue = {start}, deque([start])
    while queue:
        x,y = queue.popleft()
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            point = x+dx,y+dy
            if 0<=point[0]<n and 0<=point[1]<n and point not in blocked and point not in reached:
                reached.add(point)
                queue.append(point)
    if any(tuple(p) not in reached for p in layout["places"].values()) or any((p["x"],p["y"]) not in reached for p in people):
        raise ValueError("All places and resident spawns must connect to the park")
    return layout


def populate(layout, count):
    layout = copy.deepcopy(layout)
    if type(count) is not int or not 5 <= count <= 25:
        raise ValueError("Population must be between 5 and 25 residents")
    occupied = obstacle_cells(layout) | {(p["x"],p["y"]) for p in layout["residents"]}
    for b in layout["buildings"]:
        occupied.update((x,y) for x in range(b["x"]-2,b["x"]+2) for y in range(b["y"]-2,b["y"]+2))
    names = ["Asha","Leo","Mina","Omar","Iris","Theo","Nadia","Arun","Sofia","Rafi","Lina","Hugo","Zara","Emil","Nila","Ben","Tara","Yuki","Rosa","Eli"]
    roles = ["Baker","Musician","Librarian","Carpenter","Student"]
    free = [(x,y) for y in range(layout["size"]) for x in range(layout["size"]) if (x,y) not in occupied]
    layout["residents"] = layout["residents"][:6]
    for i in range(count-5):
        x,y = free[i*2]
        layout["residents"].append({"id":names[i].lower(),"name":names[i],"role":roles[i%5],
            "bio":f"I enjoy {['baking bread','playing music','reading stories','making furniture','learning new things'][i%5]} and meeting my neighbors.",
            "skin":SKINS[i%5],"x":x,"y":y,"plan":[{"place":p,"activity":a} for p,a in [("park","Taking a morning walk"),("cafe","Meeting neighbors"),("home","Resting")]]})
    return validate(layout)


def interiors():
    return {
        "cafe": {"size":6,"door":[2,5],"objects":[{"id":"coffee-table","name":"Cafe table","x":3,"y":2,"i":5,"w":55,"need":"social"},{"id":"cafe-chair","name":"Cafe chair","x":1,"y":2,"i":6,"w":28,"need":"energy"}]},
        "shop": {"size":6,"door":[2,5],"objects":[{"id":"bookshelf","name":"Bookshelf","x":2,"y":1,"i":9,"w":65,"need":"social"}]},
        "home": {"size":6,"door":[2,5],"objects":[{"id":"bed","name":"Bed","x":3,"y":1,"i":11,"w":70,"need":"energy"}]},
        "studio": {"size":6,"door":[2,5],"objects":[{"id":"armchair","name":"Armchair","x":2,"y":1,"i":10,"w":55,"need":"energy"}]}}
