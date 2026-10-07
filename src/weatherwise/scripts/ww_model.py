"""What every weather source is turned into before it is printed."""
import re
from dataclasses import dataclass, field


@dataclass
class Place:
    name: str
    lat: float
    lon: float
    timezone: str | None = None


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
    alerts: list[str] | None  # None means this source has no alert data for the place
    raw: dict = field(default_factory=dict)


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
