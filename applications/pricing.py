"""A rough market price for a design order, in US dollars.

Real prices in Uzbekistan depend on a lot (the architect, the details, the city), so this
gives a *range*, built from typical per-square-metre rates:

* what is built (yard/house plot, flat, office, restaurant, wedding hall),
* what is needed (architecture project, or interior design),
* the size (small objects cost more per m², big ones less),
* the number of rooms (more rooms = more drawing work),
* the place (Tashkent is dearest; other cities and regions are cheaper).

Rates are meant to be neither cheap nor expensive: the middle of what studios ask.
"""
import re

from architects.models import ObjectType, ServiceType

# (lowest, highest) US dollars per m² for a Tashkent object of 60–120 m².
RATES = {
    (ObjectType.YARD, ServiceType.ARCHITECTURE): (7, 12),
    (ObjectType.APARTMENT, ServiceType.ARCHITECTURE): (4, 8),
    (ObjectType.OFFICE, ServiceType.ARCHITECTURE): (7, 12),
    (ObjectType.RESTAURANT, ServiceType.ARCHITECTURE): (9, 15),
    (ObjectType.WEDDING_HALL, ServiceType.ARCHITECTURE): (8, 13),
    (ObjectType.YARD, ServiceType.INTERIOR): (12, 22),
    (ObjectType.APARTMENT, ServiceType.INTERIOR): (12, 22),
    (ObjectType.OFFICE, ServiceType.INTERIOR): (10, 18),
    (ObjectType.RESTAURANT, ServiceType.INTERIOR): (16, 28),
    (ObjectType.WEDDING_HALL, ServiceType.INTERIOR): (13, 23),
}

TASHKENT = re.compile(r"toshkent|tashkent|ташкент", re.IGNORECASE)
MINIMUM = 250          # no project is quoted below this
STEP = 50              # prices are rounded to the nearest 50 dollars


def _region_factor(location: str) -> float:
    return 1.0 if TASHKENT.search(location or "") else 0.85


def _size_factor(size_m2: int) -> float:
    for limit, factor in ((60, 1.15), (120, 1.0), (250, 0.9), (500, 0.8), (1000, 0.7)):
        if size_m2 <= limit:
            return factor
    return 0.6


def _rooms_factor(rooms: int) -> float:
    return min(1.3, max(0.9, 1 + 0.04 * (rooms - 3)))


def _round(value: float) -> int:
    return int(round(value / STEP)) * STEP


def estimate_price(size_m2, object_type, service_type, rooms, location):
    """Return ``(low, high)`` in dollars, or None when something needed is missing/unknown."""
    rates = RATES.get((object_type, service_type))
    try:
        size_m2, rooms = int(size_m2), int(rooms)
    except (TypeError, ValueError):
        return None
    if rates is None or size_m2 <= 0 or rooms <= 0:
        return None
    factor = _region_factor(location) * _size_factor(size_m2) * _rooms_factor(rooms)
    low = max(MINIMUM, _round(size_m2 * rates[0] * factor))
    high = max(low + STEP, _round(size_m2 * rates[1] * factor))
    return low, high
