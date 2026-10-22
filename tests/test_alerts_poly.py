import copy
import json
from datetime import datetime, timezone

import pytest

import ww_alerts
import ww_alerts_ca
import ww_alerts_eu
from conftest import FakeHttp, fixture
from ww_errors import WwError
from ww_model import Place

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
NIAGARA = Place("Niagara Falls", 43.09, -79.08, "America/Toronto", "ca", "Ontario")
ST_CATHARINES = Place("St. Catharines", 43.16, -79.24, "America/Toronto", "ca", "Ontario")
TORONTO = Place("多倫多", 43.65, -79.38, "America/Toronto", "ca", "Ontario")
BERLIN = Place("柏林", 52.52, 13.405, "Europe/Berlin", "de", "Berlin", "Mitte")
ATLANTIS = Place("Nowhere", 50.0, 10.0, "Europe/Berlin", "de", "Atlantis")
DE_URL = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-germany"


def eccc(data=None):
    return FakeHttp({"https://api.weather.gc.ca/collections/weather-alerts/items": json.loads(fixture("eccc.json")) if data is None else data})


def de(data=None):
    return FakeHttp({DE_URL: json.loads(fixture("meteoalarm_de.json")) if data is None else data})


def test_eccc_point_inside_polygon_gets_alert():
    (alerts,) = ww_alerts_ca.alerts_for([NIAGARA], eccc(), NOW)
    assert [a.key for a in alerts] == ["eccc:164551675816897565202610200503_fea1-1274"]
    a = alerts[0]
    assert (a.kind, a.severity, a.title, a.source) == ("cold", "minor", "Frost Advisory", "eccc")
    assert a.expires == datetime(2026, 10, 22, 14, 4, 58, 708000, tzinfo=timezone.utc)
    assert a.updated.tzinfo is not None and "Niagara Falls" in a.summary and len(a.summary) <= 60


def test_eccc_point_outside_gets_none_listed():
    assert ww_alerts_ca.alerts_for([TORONTO], eccc(), NOW) == [[]]


def test_eccc_one_bbox_request_for_two_places():
    h = eccc()
    out = ww_alerts_ca.alerts_for([NIAGARA, ST_CATHARINES], h, NOW)
    assert len(h.calls) == 1 and [len(x) for x in out] == [1, 1]
    assert out[0][0].key != out[1][0].key
    url = h.calls[0][0]
    assert "bbox=-79.74,42.59,-78.58,43.66" in url and "limit=500" in url and "f=json" in url


def test_eccc_multipolygon_any_part_counts():
    data = json.loads(fixture("eccc.json"))
    f = data["features"][0]
    ring = f["geometry"]["coordinates"]
    far = [[[0, 0], [0, 1], [1, 1], [0, 0]]]
    f["geometry"] = {"type": "MultiPolygon", "coordinates": [far, ring]}
    (alerts,) = ww_alerts_ca.alerts_for([NIAGARA], eccc(data), NOW)
    assert len(alerts) == 1


def test_eccc_unknown_type_listed_and_malformed_skipped():
    data = json.loads(fixture("eccc.json"))
    odd = copy.deepcopy(data["features"][0])
    odd["id"] = "odd"
    odd["properties"].update(alert_name_en="strange thing warning", risk_colour_en="red")
    bad_time = copy.deepcopy(odd)
    bad_time["id"] = "bad"
    bad_time["properties"]["expiration_datetime"] = "not a time"
    no_geom = {"id": "x", "properties": odd["properties"]}
    data["features"] = [bad_time, no_geom, {"junk": 1}, odd]
    (alerts,) = ww_alerts_ca.alerts_for([NIAGARA], eccc(data), NOW)
    assert [(a.key, a.kind, a.severity) for a in alerts] == [("eccc:odd", "other", "severe")]


def test_eccc_registered():
    assert ww_alerts.PROVIDERS["ca"] is ww_alerts_ca.alerts_for


def test_meteoalarm_berlin_gets_only_its_region():
    (alerts,) = ww_alerts_eu.alerts_for([BERLIN], de(), NOW)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.key.startswith("meteoalarm:2.49.0.0.276.0.DWD.") and a.source == "meteoalarm"
    assert (a.kind, a.severity, a.title) == ("fog", "minor", "fog")
    assert a.summary == "Official WARNING of FOG"
    assert a.expires == datetime.fromisoformat("2026-10-17T09:00:00+02:00")
    assert a.updated == datetime.fromisoformat("2026-10-17T05:50:00+02:00")


def test_meteoalarm_unknown_region_is_none():
    assert ww_alerts_eu.alerts_for([ATLANTIS], de(), NOW) == [None]


def test_meteoalarm_one_request_per_country():
    h = de()
    out = ww_alerts_eu.alerts_for([BERLIN, ATLANTIS], h, NOW)
    assert len(h.calls) == 1 and h.calls[0][0] == DE_URL
    assert out[0] and out[1] is None


def test_meteoalarm_non_met_category_is_dropped():
    data = json.loads(fixture("meteoalarm_de.json"))
    for w in data["warnings"]:
        for i in w["alert"]["info"]:
            i["category"] = ["Safety"]
    assert ww_alerts_eu.alerts_for([BERLIN], de(data), NOW) == [None]


def test_meteoalarm_polygon_area_uses_point_in_polygon():
    data = json.loads(fixture("meteoalarm_de.json"))
    info = data["warnings"][0]["alert"]["info"]
    for i in info:
        i["area"] = [{"areaDesc": "somewhere", "polygon": "52.0,13.0 52.0,14.0 53.0,14.0 53.0,13.0 52.0,13.0"}]
    (alerts,) = ww_alerts_eu.alerts_for([BERLIN], de(data), NOW)
    assert len(alerts) == 1
    far = Place("Hamburg", 53.55, 9.99, "Europe/Berlin", "de", "Hamburg")
    assert ww_alerts_eu.alerts_for([far], de(data), NOW) == [[]]


def test_meteoalarm_unknown_event_listed_and_malformed_skipped():
    data = json.loads(fixture("meteoalarm_de.json"))
    good = copy.deepcopy(data["warnings"][0])
    good["alert"]["identifier"] = "odd"
    for i in good["alert"]["info"]:
        i["event"] = "mystery"
        i["parameter"] = []
    naive = copy.deepcopy(good)
    naive["alert"]["identifier"] = "naive"
    for i in naive["alert"]["info"]:
        i["expires"] = "2026-10-17T09:00:00"
    data["warnings"] = [naive, {"alert": {}}, {"junk": 1}, good]
    (alerts,) = ww_alerts_eu.alerts_for([BERLIN], de(data), NOW)
    assert [(a.key, a.kind, a.title) for a in alerts] == [("meteoalarm:odd", "other", "mystery")]


def test_meteoalarm_falls_back_to_first_info_without_english():
    data = json.loads(fixture("meteoalarm_de.json"))
    data["warnings"][0]["alert"]["info"] = [i for i in data["warnings"][0]["alert"]["info"] if i["language"].startswith("de")]
    (alerts,) = ww_alerts_eu.alerts_for([BERLIN], de(data), NOW)
    assert alerts[0].title == "NEBEL" and alerts[0].kind == "fog"


def test_meteoalarm_countries_registered():
    assert ww_alerts_eu.COUNTRIES["de"] == "germany" and ww_alerts_eu.COUNTRIES["gb"] == "united-kingdom"
    for cc in ww_alerts_eu.COUNTRIES:
        assert ww_alerts.PROVIDERS[cc] is ww_alerts_eu.alerts_for


def test_meteoalarm_fetch_failure_raises():
    with pytest.raises(WwError):
        ww_alerts_eu.alerts_for([BERLIN], FakeHttp({DE_URL: WwError("network_error", "x")}), NOW)
