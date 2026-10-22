import json
from datetime import datetime, timedelta, timezone

import pytest

import ww_alerts
import ww_alerts_tw
import ww_cyclones
from conftest import FakeHttp, fixture
from ww_model import Place

# gdacs_list.json / gdacs_geometry.json: CHAMPI-26 (episode 33) is the real GDACS response of
# 2026-10-22, trimmed to the centroid, forecast LineStrings and Poly_Green polygons. No other
# current event existed that day, so VANCE-26 (eventid 1001339) is a reconstructed far-away
# eastern Pacific entry: CHAMPI's record with new id, name, position and a different geometry URL.
GDACS_NOW = datetime(2026, 10, 22, 12, 30, tzinfo=timezone.utc)
TAIPEI = Place("台北市", 25.033, 121.565, "Asia/Taipei", "tw", "臺北市", "中正區")
JIAOXI = Place("礁溪鄉", 24.827, 121.775, "Asia/Taipei", "tw", "宜蘭縣", "礁溪鄉")
BERLIN = Place("柏林", 52.52, 13.405, "Europe/Berlin", "de")
GEO = "https://www.gdacs.org/gdacsapi/api/polygons/getgeometry?eventtype=TC&eventid="


def http():
    return FakeHttp({
        ww_cyclones.LIST_URL: json.loads(fixture("gdacs_list.json")),
        GEO + "1001338": json.loads(fixture("gdacs_geometry.json")),
    })


def names(found):
    return {c.name: idx for c, idx in found}


def test_champi_is_near_taipei_and_jiaoxi():
    found = ww_cyclones.nearby([TAIPEI, JIAOXI], http(), GDACS_NOW)
    assert names(found) == {"CHAMPI-26": [0, 1]}
    c = found[0][0]
    assert c.level == "Red" and (c.lat, c.lon) == (21.2, 124.9)
    assert c.track[0] == (22.4, 123.9) and c.track[-1][0] > 30  # chained from the centroid outward
    assert c.wind_polygons and "296" in c.severity_text


def test_far_cyclone_is_ignored_and_its_geometry_not_fetched():
    h = http()
    ww_cyclones.nearby([TAIPEI], h, GDACS_NOW)
    urls = [u for u, _ in h.calls]
    assert GEO + "1001338" in "".join(urls) and "1001339" not in "".join(urls)


def test_cyclone_not_near_berlin():
    h = http()
    assert ww_cyclones.nearby([BERLIN], h, GDACS_NOW) == []
    assert [u for u, _ in h.calls] == [ww_cyclones.LIST_URL]  # nothing within FETCH_KM


def test_old_events_are_ignored():
    assert ww_cyclones.nearby([TAIPEI], http(), GDACS_NOW + timedelta(days=3)) == []


def test_not_current_events_are_ignored():
    data = json.loads(fixture("gdacs_list.json"))
    data["features"][0]["properties"]["iscurrent"] = "false"
    h = FakeHttp({ww_cyclones.LIST_URL: data})
    assert ww_cyclones.nearby([TAIPEI], h, GDACS_NOW) == []


def test_describe_has_distance_bearing_and_no_time():
    (c, _), = ww_cyclones.nearby([TAIPEI], http(), GDACS_NOW)
    text = ww_cyclones.describe(c, TAIPEI)
    assert text.startswith("CHAMPI-26 (GDACS Red): now ~")
    assert " SE, forecast closest ~" in text and text.endswith(" km")
    assert ":" not in text.split(": ", 1)[1]
    for part in text.split("~")[1:]:
        assert int(part.split()[0]) % 10 == 0


def test_gdacs_list_parsed_once_for_many_places():
    h = http()
    ww_cyclones.nearby([TAIPEI, JIAOXI, BERLIN], h, GDACS_NOW)
    assert [u for u, _ in h.calls].count(ww_cyclones.LIST_URL) == 1


def test_unreadable_geometry_skips_only_that_event():
    h = FakeHttp({ww_cyclones.LIST_URL: json.loads(fixture("gdacs_list.json")),
                  GEO + "1001338": RuntimeError("boom")})
    assert ww_cyclones.nearby([TAIPEI], h, GDACS_NOW) == []


def test_chain_orders_segments_from_the_centre_outward():
    a, b, c = (1.0, 1.0), (2.0, 2.0), (3.0, 3.0)
    assert ww_cyclones._chain([[c, b], [b, a]], a) == [b, c]


def test_gdacs_cyclone_merges_into_the_ncdr_typhoon_alert():
    h = FakeHttp({
        ww_alerts_tw.FEED: fixture("ncdr.xml"),
        ww_cyclones.LIST_URL: json.loads(fixture("gdacs_list.json")),
        GEO + "1001338": json.loads(fixture("gdacs_geometry.json")),
    })
    now = datetime(2026, 10, 22, 20, 30, tzinfo=timezone(timedelta(hours=8)))
    res, standalone = ww_alerts.collect([JIAOXI], h, now)
    typhoon = [a for a in res[0].alerts if a.kind == "typhoon"]
    assert typhoon and typhoon[0].cyclone.name == "CHAMPI-26"
    assert standalone == []
