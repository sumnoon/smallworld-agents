"""Bounded hierarchical task interpretation. Execution stays in the world."""
import re
from .model import object_schema, TEXT, normalize_place_names

STEP = object_schema({"kind":{"type":"string","enum":["deliver","visit","meet","wait","report","use","inspect","invite","unsupported"]},
    "recipient":TEXT,"place":TEXT,"item":TEXT,"minutes":{"type":"integer"},"guests":{"type":"array","items":TEXT},"at":{"type":"integer"}})
PLAN = object_schema({"steps":{"type":"array","items":STEP},"reply":TEXT})


def interpret(model, context):
    if model.mode != "demo":
        result = model._call("Translate the request into 1-6 ordered executable steps. Each step depends on the previous one. "
            "Use exact supplied resident/place/object IDs. Supported: deliver coffee/parcel, visit, meet, wait 1-30 minutes, report back to visitor, "
            "use or inspect an interior object (item = object ID, place = room), invite named guests to a place at a future time. "
            "Invite at is an absolute simulated timestamp in seconds; consider context.time. Invitation acceptance and attendance are separate world outcomes. "
            "Unused strings empty, arrays empty, integers zero. Unsupported or ambiguous requests return one unsupported step and a clarification reply. "
            "Do not invent capabilities or accept unspecified recipients. The world validates every step.", context, PLAN)
        return {"kind":"sequence", **result}
    text = normalize_place_names(context["request"].lower().replace("sameer", "samir"))
    parts = re.split(r"\s+(?:and then|then|and report back|and come back)\s*",text)
    if "and report back" in text or "and come back" in text:
        parts = [parts[0], "report back"]
    steps = []
    for part in parts:
        step = {"kind":"unsupported","recipient":"","place":"","item":"","minutes":0,"guests":[],"at":0}
        if "report back" in part or "come back" in part:
            step.update(kind="report",recipient="visitor")
        elif "invite" in part:
            guests = [p["id"] for p in context["residents"] if p["id"] not in (context["agent"]["id"],"visitor") and re.search(r"\b"+re.escape(p["name"].lower())+r"\b",part)]
            number = re.search(r"invite\s+(\d+|three|two)\s+residents",part)
            if number:
                count = {"three":3,"two":2}.get(number[1],int(number[1]) if number[1].isdigit() else 0)
                guests = [p["id"] for p in context["residents"] if p["id"] not in (context["agent"]["id"],"visitor")][:count]
            when = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",part)
            at = 0
            if when and 0 <= int(when[1]) <= 23 and int(when[2] or 0) < 60:
                hour = int(when[1])
                if when[3]:
                    hour = hour%12 + (12 if when[3]=="pm" else 0)
                at = int(context["time"]//86400)*86400 + hour*3600 + int(when[2] or 0)*60
                if at <= context["time"]:
                    at += 86400
            step.update(kind="invite",guests=guests,place=next((p for p in context["places"] if p in part),""),at=at)
        elif re.search(r"\b(?:use|inspect|sit|sleep|read)\b",part):
            obj = next((o for o in context.get("objects",[]) if o["id"] in part or o["name"].lower() in part),None)
            if obj:
                step.update(kind="inspect" if "inspect" in part else "use",item=obj["id"],place=obj["room"])
        else:
            step.update(model.simple_task({**context,"request":part}))
            step.pop("reply",None)
        steps.append(step)
    if len(steps)==1 and steps[0]["kind"] in ("deliver","visit","meet","wait","unsupported"):
        return {**steps[0],"reply":"Please specify a supported action, its recipient or destination, and any meeting time."}
    return {"kind":"sequence","steps":steps,"reply":"Please specify a supported action and its destination."}
