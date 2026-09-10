"""Portable scenario validation and original procedural town population."""
import copy
import re

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
    if set(layout.get("places", {})) != {"cafe", "shop", "park", "home", "studio"}:
        raise ValueError("Scenario must contain cafe, shop, park, home and studio")
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
    return layout


def populate(layout, count):
    layout = copy.deepcopy(layout)
    if type(count) is not int or not 5 <= count <= 25:
        raise ValueError("Population must be between 5 and 25 residents")
    occupied = {(p["x"],p["y"]) for p in layout["residents"]+layout["props"]}
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
