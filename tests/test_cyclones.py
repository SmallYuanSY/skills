import json
from datetime import datetime, timedelta, timezone

import pytest

import ww_alerts
import ww_alerts_tw
import ww_cyclones
import ww_geo
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
    assert [u for u, _ in h.calls] == [ww_cyclones.LIST_URL, GEO + "1001338&episodeid=33"]


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


def test_unreadable_geometry_still_reports_the_storm_by_its_centroid():
    h = FakeHttp({ww_cyclones.LIST_URL: json.loads(fixture("gdacs_list.json")),
                  GEO + "1001338": RuntimeError("boom")})
    (c, idx), = ww_cyclones.nearby([TAIPEI, BERLIN], h, GDACS_NOW)
    assert c.name == "CHAMPI-26" and c.level == "Red" and (c.lat, c.lon) == (21.2, 124.9)
    assert c.track == [] and c.wind_polygons == [] and idx == [0]  # Taipei ~550 km from the centroid


def test_unreadable_geometry_never_presents_current_distance_as_forecast():
    h = FakeHttp({ww_cyclones.LIST_URL: json.loads(fixture("gdacs_list.json")),
                  GEO + "1001338": RuntimeError("boom")})
    (c, _), = ww_cyclones.nearby([TAIPEI], h, GDACS_NOW)
    one = ww_cyclones.describe(c, TAIPEI)
    many = ww_cyclones.describe_many(c, [(0, TAIPEI), (1, JIAOXI)])
    for text in (one, many):
        assert "forecast track unavailable" in text and "forecast closest" not in text
        assert text.startswith("CHAMPI-26 (GDACS Red): now ~")


def test_garbage_geometry_is_not_cached(tmp_path):
    from ww_cache import Cached
    ts = int(GDACS_NOW.timestamp())
    bad = FakeHttp({ww_cyclones.LIST_URL: json.loads(fixture("gdacs_list.json")), GEO + "1001338": "<html>busy"})
    ww_cyclones.nearby([TAIPEI], Cached(bad, ts, tmp_path), GDACS_NOW)
    good = FakeHttp({ww_cyclones.LIST_URL: json.loads(fixture("gdacs_list.json")),
                     GEO + "1001338": json.loads(fixture("gdacs_geometry.json"))})
    (c, _), = ww_cyclones.nearby([TAIPEI], Cached(good, ts + 60, tmp_path), GDACS_NOW)
    assert any(u.startswith(GEO + "1001338") for u, _ in good.calls) and c.track


def test_unreadable_geometry_lists_the_storm_for_every_place_within_fetch_km():
    """R24: without geometry there is no track to judge by, so the storm must not silently disappear."""
    h = FakeHttp({ww_cyclones.LIST_URL: json.loads(fixture("gdacs_list.json")),
                  GEO + "1001338": RuntimeError("timeout")})
    hanoi = Place("河內", 21.03, 105.85, "Asia/Bangkok", "vn")
    km = ww_geo.distance_km(hanoi.lat, hanoi.lon, 21.2, 124.9)
    assert ww_cyclones.NEAR_KM < km < ww_cyclones.FETCH_KM
    (c, idx), = ww_cyclones.nearby([hanoi, BERLIN], h, GDACS_NOW)
    assert c.name == "CHAMPI-26" and idx == [0]  # Berlin is beyond FETCH_KM
    text = ww_cyclones.describe(c, hanoi)
    assert text.startswith("CHAMPI-26 (GDACS Red): now ~") and text.endswith("forecast track unavailable")


def test_rejected_geometry_body_also_lists_the_storm_within_fetch_km():
    h = FakeHttp({ww_cyclones.LIST_URL: json.loads(fixture("gdacs_list.json")),
                  GEO + "1001338": {"error": "busy"}})
    hanoi = Place("河內", 21.03, 105.85, "Asia/Bangkok", "vn")
    assert names(ww_cyclones.nearby([hanoi], h, GDACS_NOW)) == {"CHAMPI-26": [0]}


def test_readable_geometry_still_uses_near_km():
    hanoi = Place("河內", 21.03, 105.85, "Asia/Bangkok", "vn")  # ~2000 km, track never within 800 km
    assert ww_cyclones.nearby([hanoi], http(), GDACS_NOW) == []


def test_malformed_list_entry_skips_only_that_entry():
    data = json.loads(fixture("gdacs_list.json"))
    bad = json.loads(json.dumps(data["features"][0]))
    del bad["geometry"]
    worse = json.loads(json.dumps(data["features"][0]))
    del worse["properties"]["eventname"]
    data["features"] = [bad, worse] + data["features"]
    h = FakeHttp({ww_cyclones.LIST_URL: data, GEO + "1001338": json.loads(fixture("gdacs_geometry.json"))})
    assert names(ww_cyclones.nearby([TAIPEI], h, GDACS_NOW)) == {"CHAMPI-26": [0]}


def _synthetic(polygon=None):
    """A storm at 0N 0E with no track, optionally with a square wind area around (0, 1.0)."""
    feat = {"geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
            "properties": {"iscurrent": "true", "todate": "2026-10-22T12:00:00", "eventname": "TEST-26",
                           "alertlevel": "Orange", "url": {"geometry": GEO + "1"}}}
    geo = {"features": [{"geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                         "properties": {"Class": "Point_Centroid"}}]}
    if polygon:
        geo["features"].append({"geometry": {"type": "Polygon", "coordinates": [polygon]},
                                "properties": {"Class": "Poly_Green"}})
    return FakeHttp({ww_cyclones.LIST_URL: {"features": [feat]}, GEO + "1": geo})


def test_place_inside_a_wind_polygon_matches_beyond_near_km():
    place = Place("x", 0.0, 10.0)  # ~1100 km from the centroid
    ring = [[9.0, -1.0], [11.0, -1.0], [11.0, 1.0], [9.0, 1.0], [9.0, -1.0]]  # [lon, lat]
    assert ww_geo.distance_km(0, 0, 0, 10) > ww_cyclones.NEAR_KM
    assert names(ww_cyclones.nearby([place], _synthetic(ring), GDACS_NOW)) == {"TEST-26": [0]}
    assert ww_cyclones.nearby([place], _synthetic(), GDACS_NOW) == []  # same place, no polygon


def test_place_just_beyond_near_km_is_not_matched_and_just_inside_is():
    deg = ww_cyclones.NEAR_KM / ww_geo.distance_km(0, 0, 0, 1)
    assert ww_cyclones.nearby([Place("x", 0.0, deg * 1.02)], _synthetic(), GDACS_NOW) == []
    assert names(ww_cyclones.nearby([Place("x", 0.0, deg * 0.98)], _synthetic(), GDACS_NOW)) == {"TEST-26": [0]}


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
    res, standalone, _ = ww_alerts.collect([JIAOXI], h, now)
    typhoon = [a for a in res[0].alerts if a.kind == "typhoon"]
    assert typhoon and typhoon[0].cyclone.name == "CHAMPI-26"
    assert standalone == []


def test_far_centroid_with_a_track_passing_close_is_matched():
    h = _synthetic()
    h.routes[GEO + "1"]["features"].append({"geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [22.0, 0.0]]},
                                            "properties": {"Class": "Line_Line_0", "forecast": True}})
    place = Place("x", 0.0, 22.5)
    assert 2400 < ww_geo.distance_km(0, 0, 0, 22.5) < ww_cyclones.FETCH_KM
    assert names(ww_cyclones.nearby([place], h, GDACS_NOW)) == {"TEST-26": [0]}


def test_tokyo_alone_gets_champi_whose_track_passes_close():
    tokyo = Place("東京", 35.68, 139.69, "Asia/Tokyo", "jp", "東京都", "千代田区")
    assert ww_geo.distance_km(tokyo.lat, tokyo.lon, 21.2, 124.9) > 2000  # beyond the old fetch radius
    assert "CHAMPI-26" in names(ww_cyclones.nearby([tokyo], http(), GDACS_NOW))


def test_gdacs_no_content_means_no_cyclone_not_unavailable():
    # GDACS answers 204 No Content when no event matches (probed 2026-10-23); ww_http turns that into None
    h = FakeHttp({ww_cyclones.LIST_URL: lambda u: None, ww_alerts_tw.FEED: fixture("ncdr.xml")})
    got = ww_alerts.collect([TAIPEI], h, GDACS_NOW)
    assert (got.cyclones, got.cyclone_error) == ([], None)


def test_a_todate_with_its_own_offset_keeps_it():
    data = json.loads(fixture("gdacs_list.json"))
    data["features"][0]["properties"]["todate"] = "2026-10-21T20:00:00+08:00"  # 12:00Z, 24.5 h before now
    h = FakeHttp({ww_cyclones.LIST_URL: data, GEO + "1001338": json.loads(fixture("gdacs_geometry.json"))})
    assert ww_cyclones.nearby([TAIPEI], h, GDACS_NOW) == []
    data["features"][0]["properties"]["todate"] = "2026-10-22T08:00:00+08:00"  # 00:00Z, 12.5 h before
    assert names(ww_cyclones.nearby([TAIPEI], h, GDACS_NOW)) == {"CHAMPI-26": [0]}
