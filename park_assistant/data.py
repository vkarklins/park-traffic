"""Stub data for the Park Trip Assistant.

Everything here is fake and deterministic so we always know the "right" answer.
That's what makes the planted bugs measurable: if the bot says something that
disagrees with this file, we know exactly why.
"""

PARKS = {
    "yosemite": {
        "name": "Yosemite National Park", "state": "CA",
        "summary": "Granite cliffs, giant sequoias, and waterfalls in the Sierra Nevada.",
        "trails": {"Mist Trail": "open", "Half Dome Cables": "closed", "Mirror Lake Loop": "open"},
    },
    "joshua tree": {
        "name": "Joshua Tree National Park", "state": "CA",
        "summary": "Desert park where the Mojave and Colorado deserts meet; famous for climbing and stargazing.",
        "trails": {"Ryan Mountain": "open", "Hidden Valley": "open", "Lost Palms Oasis": "closed"},
    },
    "zion": {
        "name": "Zion National Park", "state": "UT",
        "summary": "Red sandstone canyons carved by the Virgin River.",
        "trails": {"Angels Landing": "open", "The Narrows": "closed", "Emerald Pools": "open"},
    },
    "grand canyon": {
        "name": "Grand Canyon National Park", "state": "AZ",
        "summary": "A mile-deep canyon carved by the Colorado River.",
        "trails": {"Bright Angel": "open", "South Kaibab": "open", "North Kaibab": "closed"},
    },
    "yellowstone": {
        "name": "Yellowstone National Park", "state": "WY",
        "summary": "The first national park; geysers, hot springs, and bison herds.",
        "trails": {"Fairy Falls": "open", "Mount Washburn": "open", "Lone Star Geyser": "closed"},
    },
    "glacier": {
        "name": "Glacier National Park", "state": "MT",
        "summary": "Glacier-carved peaks and the Going-to-the-Sun Road in Montana.",
        "trails": {"Highline Trail": "open", "Grinnell Glacier": "closed", "Avalanche Lake": "open"},
    },
    "glacier bay": {
        "name": "Glacier Bay National Park", "state": "AK",
        "summary": "Tidewater glaciers and fjords in southeast Alaska, mostly reached by boat.",
        "trails": {"Forest Loop": "open", "Bartlett River": "open"},
    },
    "rocky mountain": {
        "name": "Rocky Mountain National Park", "state": "CO",
        "summary": "High alpine terrain along the Continental Divide.",
        "trails": {"Sky Pond": "open", "Emerald Lake": "open", "Longs Peak Keyhole": "closed"},
    },
    "acadia": {
        "name": "Acadia National Park", "state": "ME",
        "summary": "Rocky Atlantic coastline and Cadillac Mountain.",
        "trails": {"Beehive": "closed", "Jordan Pond Path": "open", "Ocean Path": "open"},
    },
    "olympic": {
        "name": "Olympic National Park", "state": "WA",
        "summary": "Rainforest, rugged coastline, and glaciated mountains.",
        "trails": {"Hoh River": "open", "Hurricane Hill": "open", "Enchanted Valley": "closed"},
    },
}

# Details for every trail in PARKS: round-trip length (miles), difficulty, and
# a one-line conditions note. check_trail_status returns these with the status.
TRAIL_DETAILS = {
    "yosemite": {
        "Mist Trail": (5.4, "strenuous", "Wet, slippery granite steps near Vernal Fall; bring a rain layer."),
        "Half Dome Cables": (16.0, "very strenuous", "Closed: cables are down for the season."),
        "Mirror Lake Loop": (5.0, "easy", "Mostly flat; the lake is shallow by late summer."),
    },
    "joshua tree": {
        "Ryan Mountain": (3.0, "moderate", "Steady climb with no shade; carry plenty of water."),
        "Hidden Valley": (1.0, "easy", "Short loop among boulders; popular with climbers."),
        "Lost Palms Oasis": (7.2, "moderate", "Closed: washout damage on the trail."),
    },
    "zion": {
        "Angels Landing": (5.4, "very strenuous", "Permit required for the chains section; steep drop-offs."),
        "The Narrows": (9.4, "strenuous", "Closed: river flow is too high to wade safely."),
        "Emerald Pools": (3.0, "easy", "Upper pool section can be muddy after rain."),
    },
    "grand canyon": {
        "Bright Angel": (9.0, "strenuous", "Water stations open; avoid hiking down in midday heat."),
        "South Kaibab": (6.0, "strenuous", "No water on the trail; very exposed."),
        "North Kaibab": (14.0, "very strenuous", "Closed: North Rim road is closed for the season."),
    },
    "yellowstone": {
        "Fairy Falls": (5.4, "easy", "Flat; side spur to the Grand Prismatic overlook."),
        "Mount Washburn": (6.4, "moderate", "Windy summit; bighorn sheep are often seen."),
        "Lone Star Geyser": (4.8, "easy", "Closed: bear activity in the area."),
    },
    "glacier": {
        "Highline Trail": (11.8, "strenuous", "Narrow ledge section at the start; snow possible early season."),
        "Grinnell Glacier": (10.6, "strenuous", "Closed: snowfield crossing is unsafe."),
        "Avalanche Lake": (4.5, "easy", "Shaded forest walk; busy by mid-morning."),
    },
    "glacier bay": {
        "Forest Loop": (1.0, "easy", "Boardwalk through rainforest near Bartlett Cove."),
        "Bartlett River": (4.0, "easy", "Muddy in places; watch for bears near the river."),
    },
    "rocky mountain": {
        "Sky Pond": (9.0, "strenuous", "Short rock scramble beside Timberline Falls."),
        "Emerald Lake": (3.2, "easy", "Passes Nymph and Dream Lakes; crowded on weekends."),
        "Longs Peak Keyhole": (14.5, "very strenuous", "Closed: icy conditions on the route."),
    },
    "acadia": {
        "Beehive": (1.5, "strenuous", "Closed: peregrine falcon nesting."),
        "Jordan Pond Path": (3.3, "easy", "Flat loop around the pond; some boardwalk sections."),
        "Ocean Path": (4.4, "easy", "Coastal walk past Thunder Hole; best near high tide."),
    },
    "olympic": {
        "Hoh River": (10.6, "moderate", "Flat rainforest trail; often muddy."),
        "Hurricane Hill": (3.2, "moderate", "Paved, steady climb; views of the Strait of Juan de Fuca."),
        "Enchanted Valley": (26.0, "strenuous", "Closed: bridge washed out."),
    },
}

# Dates (YYYY-MM-DD) when a park's campgrounds are genuinely full.
# This drives the DECOY scenarios: users get frustrated, but nothing is broken.
SOLD_OUT = {
    "yosemite": {"2027-07-03", "2027-07-04", "2027-07-05"},
    "zion": {"2027-05-29", "2027-05-30"},
    "grand canyon": {"2027-06-19", "2027-06-20"},
    "yellowstone": {"2027-07-04", "2027-08-14"},
    "acadia": {"2027-08-07"},
}

# Campgrounds per park: name -> amenities. Availability lists them; booking
# assigns a site at one of them (the visitor's choice, or the first listed).
CAMPGROUNDS = {
    "yosemite": {"Upper Pines": "flush toilets, drinking water, fire rings, bear lockers",
                 "Wawona": "flush toilets, drinking water, fire rings, riverside sites"},
    "joshua tree": {"Jumbo Rocks": "vault toilets, fire rings, picnic tables; no water",
                    "Black Rock": "flush toilets, drinking water, fire rings"},
    "zion": {"Watchman": "flush toilets, drinking water, fire rings, some electric hookups",
             "South": "flush toilets, drinking water, fire rings, shuttle stop nearby"},
    "grand canyon": {"Mather": "flush toilets, drinking water, coin showers nearby",
                     "Desert View": "flush toilets, drinking water, fire rings; no hookups"},
    "yellowstone": {"Madison": "flush toilets, drinking water, fire rings, bear boxes",
                    "Canyon": "flush toilets, drinking water, showers, laundry, bear boxes"},
    "glacier": {"Apgar": "flush toilets, drinking water, fire rings, lake access",
                "Many Glacier": "flush toilets, drinking water, fire rings, food storage lockers"},
    "glacier bay": {"Bartlett Cove": "walk-in tent sites, outhouses, bear-proof food caches"},
    "rocky mountain": {"Moraine Park": "flush toilets, drinking water, fire rings",
                       "Glacier Basin": "flush toilets, drinking water, fire rings, group loop"},
    "acadia": {"Blackwoods": "flush toilets, drinking water, fire rings, ocean nearby",
               "Seawall": "flush toilets, drinking water, fire rings, walk-in tent sites"},
    "olympic": {"Hoh": "flush toilets, drinking water, fire rings, rainforest setting",
                "Kalaloch": "flush toilets, drinking water, fire rings, beach access"},
}

MAX_PARTY_SIZE = 8  # real rule: groups larger than 8 must book a group site (we don't offer those)
