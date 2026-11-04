"""Shared geography for the hand-authored SAMPLE fixtures.

None of this is official data. The hazard polygon is a rough stand-in drawn so
the demo has a boundary to route across. `tools/record_fixtures.py` replaces
every sample response with a real recorded one before filming.
"""

DEMO_ADDRESS = "1000 Great Highway, San Francisco, CA 94121"
DEMO_DISPLAY = "Beach Chalet, 1000 Great Highway, Outer Richmond, San Francisco, California, 94121, United States"
DEMO_HOME = (-122.51005, 37.76966)

OUTSIDE_ADDRESS = "1 Dr Carlton B Goodlett Pl, San Francisco, CA 94102"
OUTSIDE_DISPLAY = "San Francisco City Hall, 1 Dr Carlton B Goodlett Place, Civic Center, San Francisco, California, 94102, United States"
OUTSIDE_HOME = (-122.41925, 37.77929)

# Ocean side to the west; the inland edge wanders between 47th and 48th Avenue.
SAMPLE_HAZARD_RING = [
    (-122.5400, 37.7400),
    (-122.5068, 37.7400),
    (-122.5072, 37.7520),
    (-122.5078, 37.7610),
    (-122.5085, 37.7680),
    (-122.5081, 37.7745),
    (-122.5090, 37.7820),
    (-122.5120, 37.7900),
    (-122.5400, 37.7900),
    (-122.5400, 37.7400),
]

# The stand-in map's "outside hazard area" land: inland of the hazard ring, sharing its inland edge.
SAMPLE_LAND_RING = [
    (-122.5068, 37.7400),
    (-122.4600, 37.7400),
    (-122.4600, 37.7900),
    (-122.5120, 37.7900),
    (-122.5090, 37.7820),
    (-122.5081, 37.7745),
    (-122.5085, 37.7680),
    (-122.5078, 37.7610),
    (-122.5072, 37.7520),
    (-122.5068, 37.7400),
]
