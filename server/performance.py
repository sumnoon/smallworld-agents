"""Conservative local parsing and small operation-specific model contexts."""
import re
from .model import normalize_place_names


def fast_task(context):
    """Return None unless the entire request matches supported, explicit grammar."""
    text = normalize_place_names(context.get("request", "").lower().strip().rstrip(".!"))
    text = re.sub(r",? please$", "", re.sub(r"^please\s+", "", text)).replace("sameer", "samir")
    people = {p["name"].lower(): p["id"] for p in context.get("residents", [])}
    people.update({p["id"]: p["id"] for p in context.get("residents", [])})
    steps = []
    for part in re.split(r"\s+(?:and then|then|and)\s+", text):
        step = None
        m = re.fullmatch(r"(?:bring|deliver|give|take) (?:a |the )?(coffee|parcel|package) to (.+)", part)
        if m and m[2] in people:
            step = {"kind":"deliver", "item":"parcel" if m[1]=="package" else m[1], "recipient":people[m[2]]}
        m = re.fullmatch(r"(?:visit|go to|walk to|head to) (?:the )?(.+)", part)
        if m and m[1] in context.get("places", {}):
            step = {"kind":"visit", "place":m[1]}
        m = re.fullmatch(r"meet (.+)", part)
        if m and m[1] in people:
            step = {"kind":"meet", "recipient":people[m[1]]}
        m = re.fullmatch(r"wait (?:for )?(\d+) (?:minutes?|mins?)", part)
        if m and 1 <= int(m[1]) <= 30:
            step = {"kind":"wait", "minutes":int(m[1])}
        if part in ("report back", "come back", "report back to me"):
            step = {"kind":"report", "recipient":"visitor"}
        if part in ("plant vegetables", "water vegetables", "harvest vegetables", "buy picnic supplies", "prepare picnic food"):
            step = {"kind":part.split()[0], "place":"market" if part.startswith("buy") else "cafe" if part.startswith("prepare") else "garden"}
        if part in ("organize a picnic", "organize a neighborhood picnic", "organise a picnic", "plan a picnic"):
            step = {"kind":"picnic"}
        if step is None:
            return None
        steps.append(step)
    if not 1 <= len(steps) <= 6:
        return None
    return {"kind":"sequence", "steps":steps, "reply":""} if len(steps)>1 else steps[0]


def compact_context(context, schema):
    fields = schema["properties"]
    task = "steps" in fields or "kind" in fields
    keys = ("agent", "request", "time", "residents", "places", "place_names", "objects") if task else ("agent", "time", "message", "conversation", "other_name", "memories", "observations", "active_task", "commitments")
    result = {k:context[k] for k in keys if k in context}
    if "place" in fields and not task:
        result["places"] = context.get("places", {})
    if "agent" in result:
        result["agent"] = {k:v for k,v in result["agent"].items() if k in ("id","name","role","bio","status","needs","plan","inventory")}
    if "memories" in result:
        result["memories"] = [{k:m[k] for k in ("id","kind","text") if k in m} for m in result["memories"][:6]]
    if isinstance(result.get("conversation"),list):
        result["conversation"] = result["conversation"][-4:]
    return result
