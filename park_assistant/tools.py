"""The chatbot's tools: plain Python functions over the stub data.

Each tool takes the model's arguments plus a context (bug config + recorder)
and returns a JSON-able dict. A tool signals failure by raising ToolError;
the chatbot catches it, records an errored tool span in Raindrop, and tells
the model the call failed.
"""

import zlib
from dataclasses import dataclass

from . import bugs as b
from .data import CAMPGROUNDS, MAX_PARTY_SIZE, PARKS, SOLD_OUT, TRAIL_DETAILS


class ToolError(Exception):
    pass


@dataclass
class ToolContext:
    """Per-conversation state the tools can see."""
    bugs: b.BugConfig
    rec: b.BugRecorder
    bookings: int = 0  # bookings made so far in this conversation


def _crc(*parts) -> int:
    return zlib.crc32("|".join(str(p) for p in parts).encode())


def _resolve_park(query: str, ctx: ToolContext) -> str:
    q = query.lower().replace("national park", "").strip()
    correct = None
    if q in PARKS:
        correct = q
    else:
        # loose match: first park whose key or name contains the query
        for key, park in PARKS.items():
            if q and (q in key or q in park["name"].lower()):
                correct = key
                break
    key = b.hook_resolve_park(query, correct, ctx.bugs, ctx.rec)
    if key is None:
        raise ToolError(f"No park found matching '{query}'.")
    return key


def search_parks(args: dict, ctx: ToolContext) -> dict:
    state = args.get("state", "").upper().strip()
    matches = [p["name"] for p in PARKS.values() if p["state"] == state]
    return {"state": state, "parks": matches}


def get_park_details(args: dict, ctx: ToolContext) -> dict:
    key = _resolve_park(args["park_name"], ctx)
    bug_error = b.hook_park_details(key, ctx.bugs, ctx.rec)
    if bug_error:
        raise ToolError(bug_error)
    park = PARKS[key]
    return {"name": park["name"], "state": park["state"], "summary": park["summary"]}


def check_trail_status(args: dict, ctx: ToolContext) -> dict:
    key = _resolve_park(args["park_name"], ctx)
    park = PARKS[key]
    details = TRAIL_DETAILS.get(key, {})
    trails = {}
    for trail, status in park["trails"].items():
        length, difficulty, notes = details.get(trail, (None, None, None))
        trails[trail] = {"status": status, "length_miles_round_trip": length,
                         "difficulty": difficulty, "conditions": notes}
    return {"park": park["name"], "trails": trails}


def _campground_list(key: str, date: str) -> list[dict]:
    # sites_open is fake but stable: the same park/campground/date always gives
    # the same count (1-24).
    return [{"name": name, "amenities": amenities,
             "sites_open": _crc(key, name, date) % 24 + 1}
            for name, amenities in CAMPGROUNDS.get(key, {}).items()]


def check_campsite_availability(args: dict, ctx: ToolContext) -> dict:
    key = _resolve_park(args["park_name"], ctx)
    date = args["date"]
    available = date not in SOLD_OUT.get(key, set())
    return {"park": PARKS[key]["name"], "date": date, "available": available,
            "campgrounds": _campground_list(key, date) if available else []}


def book_campsite(args: dict, ctx: ToolContext) -> dict:
    key = _resolve_park(args["park_name"], ctx)
    party_size = int(args["party_size"])
    date = args["date"]

    if party_size > MAX_PARTY_SIZE:
        raise ToolError(f"Party size {party_size} exceeds the {MAX_PARTY_SIZE}-person site limit. "
                        "Group sites are not bookable through this assistant.")
    bug_error = b.hook_booking_party(party_size, ctx.bugs, ctx.rec)
    if bug_error:
        raise ToolError(bug_error)

    if date in SOLD_OUT.get(key, set()):
        raise ToolError(f"No campsites available at {PARKS[key]['name']} on {date}.")

    campgrounds = CAMPGROUNDS.get(key, {})
    wanted = (args.get("campground") or "").strip()
    match = next((c for c in campgrounds if wanted and wanted.lower() in c.lower()), None)
    if wanted and match is None:
        raise ToolError(f"No campground '{wanted}' at {PARKS[key]['name']}. "
                        f"Options: {', '.join(campgrounds)}.")
    campground = match or next(iter(campgrounds))

    saved_date = b.hook_booking_date(date, ctx.bugs, ctx.rec)
    # Each booking in a conversation gets its own site and confirmation number,
    # even when the details repeat (e.g. two sites for a split group).
    ctx.bookings += 1
    crc = _crc(key, campground, saved_date, args.get("name", ""), party_size, ctx.bookings)
    confirmation = f"NPS-{crc % 100000:05d}"
    site = f"{'ABC'[crc % 3]}{crc % 40 + 1}"  # deterministic, e.g. "B14"
    return {"confirmed": True, "confirmation": confirmation, "park": PARKS[key]["name"],
            "campground": campground, "site": site, "amenities": campgrounds[campground],
            "date": saved_date, "party_size": party_size, "name": args.get("name", "")}


TOOL_FUNCTIONS = {
    "search_parks": search_parks,
    "get_park_details": get_park_details,
    "check_trail_status": check_trail_status,
    "check_campsite_availability": check_campsite_availability,
    "book_campsite": book_campsite,
}


def _fn(name, description, properties, required):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }}


TOOL_SCHEMAS = [
    _fn("search_parks", "List national parks in a US state.",
        {"state": {"type": "string", "description": "Two-letter state code, e.g. CA"}}, ["state"]),
    _fn("get_park_details", "Get a short description of a national park.",
        {"park_name": {"type": "string"}}, ["park_name"]),
    _fn("check_trail_status",
        "Get status, round-trip length, difficulty, and current conditions for a "
        "park's main trails. Takes the park name, not a trail name.",
        {"park_name": {"type": "string"}}, ["park_name"]),
    _fn("check_campsite_availability",
        "Check whether campsites are available on a date; lists the park's campgrounds, "
        "their amenities, and how many sites are open when available.",
        {"park_name": {"type": "string"},
         "date": {"type": "string", "description": "YYYY-MM-DD"}}, ["park_name", "date"]),
    _fn("book_campsite",
        "Book a standard campsite for one night. Returns the campground, site number, "
        "and amenities.",
        {"park_name": {"type": "string"},
         "date": {"type": "string", "description": "YYYY-MM-DD"},
         "party_size": {"type": "integer"},
         "name": {"type": "string", "description": "Name for the reservation"},
         "campground": {"type": "string",
                        "description": "Optional campground name; defaults to the "
                                       "park's first campground"}},
        ["park_name", "date", "party_size", "name"]),
]
