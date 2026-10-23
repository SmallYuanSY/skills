# Data sources and attribution

weatherwise never names its sources in answers. The attribution the providers require is kept here.

| Area | Source | URL | License / attribution |
|---|---|---|---|
| Forecast (default) | Open-Meteo | https://open-meteo.com | CC BY 4.0, attribution: Open-Meteo.com |
| Forecast (optional) | Apple WeatherKit | https://developer.apple.com/weatherkit/ | Apple Developer Program terms; only used when the user sets it up |
| Place search | OpenStreetMap Nominatim | https://nominatim.openstreetmap.org | ODbL, attribution: © OpenStreetMap contributors |
| Taiwan alerts | NCDR 災害示警 (CAP), issued by 中央氣象署 | https://alerts.ncdr.nat.gov.tw/RssAtomFeed.ashx | Public domain (政府資料開放授權); at most one request per 3 seconds |
| Japan alerts | 気象庁 (JMA) | https://www.jma.go.jp/bosai/warning/data/warning/ | 出典：気象庁ホームページ (government standard terms of use) |
| Europe alerts (~38 countries) | MeteoAlarm | https://feeds.meteoalarm.org/api/v1/warnings/ | MeteoAlarm.org, CC BY 4.0 |
| US alerts | National Weather Service | https://api.weather.gov/alerts/active | Public domain; requires a User-Agent |
| Canada alerts | Environment and Climate Change Canada | https://api.weather.gc.ca/collections/weather-alerts/items | Open Government Licence - Canada |
| Hong Kong alerts | Hong Kong Observatory | https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warnsum | HKO open data terms; acknowledge the Hong Kong Observatory as the source |
| Tropical cyclones (worldwide) | GDACS | https://www.gdacs.org | GDACS, European Commission / United Nations |

GDACS is track data only, not a local official warning. Cyclone output always says so and sends users to their local weather agency.
