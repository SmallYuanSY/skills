"""What every weather source is turned into before it is printed."""
import re
from dataclasses import dataclass, field
from datetime import datetime

SEVERITY_ORDER = ["extreme", "severe", "moderate", "minor"]
VARIANTS = re.compile(r" / |;")


def one_variant(label: str) -> str:
    """Nominatim's zh labels may list several script variants in one part ("德国;德國", "韩国 / 南韓");
    keep the last (zh-Hant in observed data), part by part. "Biel/Bienne" has no spaces and is kept."""
    out = []
    for part in label.split(", "):
        variants = [v.strip() for v in VARIANTS.split(part) if v.strip()]
        out.append(variants[-1] if variants else part)
    return ", ".join(out)


@dataclass
class Place:
    name: str
    lat: float
    lon: float
    timezone: str | None = None
    country_code: str | None = None  # lowercase ISO 3166-1 alpha-2
    region: str | None = None  # Taiwan county/city, Japan prefecture, US state
    locality: str | None = None  # Taiwan township/district, Japan municipality
    district: str | None = None  # county-level area outside Taiwan (German Kreis, UK county), else None


@dataclass
class Current:
    condition: str
    temperature: float
    feels_like: float
    humidity: float  # percent, 0-100
    wind_kmh: float
    uv: float | None


@dataclass
class Day:
    date: str  # YYYY-MM-DD in the place's timezone
    condition: str
    temp_min: float
    temp_max: float
    precip_chance: float | None  # percent, 0-100


@dataclass
class Report:
    source: str  # "open-meteo" or "weatherkit"
    current: Current | None
    days: list[Day]
    raw: dict = field(default_factory=dict)
    next_hour: str | None = None  # None means this source has no such data (e.g. Open-Meteo)


@dataclass
class Alert:
    kind: str
    severity: str  # one of SEVERITY_ORDER
    title: str
    summary: str  # at most 60 characters
    detail: str
    expires: datetime | None  # aware
    updated: datetime | None
    source: str  # e.g. "ncdr"
    key: str
    cyclone: "Cyclone | None" = None  # the GDACS cyclone merged into this local alert


@dataclass
class PlaceAlerts:
    status: str  # "ok", "unsupported" or "unavailable"
    alerts: list[Alert]
    reason: str = ""


@dataclass
class Cyclone:
    name: str  # e.g. "CHAMPI-26"
    level: str  # "Green", "Orange" or "Red"
    lat: float
    lon: float
    track: list[tuple[float, float]]
    wind_polygons: list[list[tuple[float, float]]]
    severity_text: str


# WMO weather codes (Open-Meteo) -> the same names WeatherKit codes produce
WMO = {
    0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Cloudy",
    45: "Foggy", 48: "Foggy",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 56: "Freezing Drizzle", 57: "Freezing Drizzle",
    61: "Rain", 63: "Rain", 65: "Heavy Rain", 66: "Freezing Rain", 67: "Freezing Rain",
    71: "Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow",
    80: "Rain", 81: "Rain", 82: "Heavy Rain", 85: "Snow", 86: "Heavy Snow",
    95: "Thunderstorms", 96: "Thunderstorms", 99: "Thunderstorms",
}


def wmo_condition(code: int) -> str:
    return WMO.get(code, f"Unknown (WMO {code})")


def weatherkit_condition(code: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", code)
