"""End-to-end API behaviour with fake routing and weather providers."""

from datetime import datetime, timedelta, timezone

import pytest
from rest_framework.test import APIClient

from api import services
from core.errors import UpstreamError
from core.forecast import HourlySeries
from core.geo import METERS_PER_MILE, RouteLine
from providers.routing import ProviderRoute, Router


def make_line(lon_offset: float, miles=300.0, mph=55.0, n=60):
    total = miles * METERS_PER_MILE
    lats = [35 + (total / 111_195) * i / (n - 1) for i in range(n)]
    lons = [-97 + lon_offset] * n
    cum_m = [total * i / (n - 1) for i in range(n)]
    cum_s = [m / (mph * METERS_PER_MILE / 3600) for m in cum_m]
    return RouteLine(lats, lons, cum_m, cum_s)


class FakeRouter(Router):
    name = "fake"
    truck_aware = True

    def __init__(self, n_routes=3):
        self.n_routes = n_routes

    def routes(self, stops, depart_utc, load_lb, max_alternatives):
        if len(stops) > 2:
            return []  # no via routes in tests
        # Separate meridians -> no overlap between routes. Route 0 is fastest.
        return [ProviderRoute(make_line(0.5 * i, miles=300 + 10 * i)) for i in range(self.n_routes)]


def fake_weather(stormy_lon=None, wind=10.0):
    """Calm everywhere, except a 50 mph wind on the route at `stormy_lon`."""

    def fetch(points, start, end, with_sources=False):
        start_h = start.replace(minute=0, second=0, microsecond=0)
        start_h = datetime(start_h.year, start_h.month, start_h.day, tzinfo=timezone.utc)
        n = int((end - start_h).total_seconds() // 3600) + 30
        out = []
        for lat, lon in points:
            w = 50.0 if stormy_lon is not None and abs(lon - stormy_lon) < 1e-6 else wind
            out.append(HourlySeries(start_h, [w] * n, [w + 5] * n, [0.0] * n, [0.0] * n))
        return (out, ["fake"]) if with_sources else out

    return fetch


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def body():
    return {
        "origin": {"label": "Oklahoma City, OK", "lat": 35.0, "lon": -97.0},
        "destination": {"label": "Kansas City, MO", "lat": 39.3, "lon": -97.0},
        "departure": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "load_lb": 35_000,
        "interval_mi": 25,
    }


def test_plan_recommends_route_avoiding_storm(client, body, monkeypatch):
    monkeypatch.setattr(services, "get_router", lambda: FakeRouter())
    # Route A (fastest, lon -97.0) gets 50 mph wind -> No Travel for a 35,000 lb load.
    monkeypatch.setattr(services, "fetch_hourly", fake_weather(stormy_lon=-97.0))
    r = client.post("/api/plan", body, format="json")
    assert r.status_code == 200, r.content
    data = r.json()
    assert len(data["routes"]) == 3
    assert data["recommendation"]["route_id"] == "B"
    # B vs runner-up C differs only in time; against A it wins on No Travel miles.
    assert data["recommendation"]["decided_by"] == "duration"
    assert data["recommendation"]["beats"] == {"C": "duration", "A": "no_travel_miles"}
    a = next(x for x in data["routes"] if x["id"] == "A")
    assert a["worst_level"] == "no_travel" and a["rank"] == 3
    assert a["checkpoints"][0]["risk"]["load_raised"] is True
    # Owned miles add up to the route length.
    for route in data["routes"]:
        assert sum(c["owned_mi"] for c in route["checkpoints"]) == pytest.approx(route["distance_mi"], abs=0.1)
        assert sum(route["miles_by_level"].values()) == pytest.approx(route["distance_mi"], abs=0.1)


def test_plan_calm_weather_fastest_wins(client, body, monkeypatch):
    monkeypatch.setattr(services, "get_router", lambda: FakeRouter())
    monkeypatch.setattr(services, "fetch_hourly", fake_weather())
    data = client.post("/api/plan", body, format="json").json()
    assert data["recommendation"]["route_id"] == "A"
    assert data["recommendation"]["decided_by"] == "duration"
    assert data["warnings"] == []


def test_fewer_routes_warns(client, body, monkeypatch):
    monkeypatch.setattr(services, "get_router", lambda: FakeRouter(n_routes=1))
    monkeypatch.setattr(services, "fetch_hourly", fake_weather())
    data = client.post("/api/plan", body, format="json").json()
    assert len(data["routes"]) == 1
    assert [w["code"] for w in data["warnings"]] == ["FEWER_ROUTES"]
    assert data["recommendation"]["decided_by"] is None


def test_eta_checkpoint_times(client, body, monkeypatch):
    monkeypatch.setattr(services, "get_router", lambda: FakeRouter(n_routes=1))
    monkeypatch.setattr(services, "fetch_hourly", fake_weather())
    data = client.post("/api/plan", body, format="json").json()
    dep = datetime.fromisoformat(data["meta"]["departure"].replace("Z", "+00:00"))
    cp = data["routes"][0]["checkpoints"][2]  # mile 50 at 55 mph
    eta = datetime.fromisoformat(cp["eta"].replace("Z", "+00:00"))
    assert cp["mile"] == 50.0
    assert (eta - dep).total_seconds() == pytest.approx(50 / 55 * 3600, abs=1)


@pytest.mark.parametrize(
    "patch, field, code",
    [
        ({"departure": "2020-01-01T00:00:00Z"}, "departure", "DEPARTURE_IN_PAST"),
        ({"departure": (datetime.now(timezone.utc) + timedelta(days=9)).isoformat()}, "departure", "DEPARTURE_TOO_FAR"),
        ({"load_lb": -5}, "load_lb", "INVALID_INPUT"),
        ({"load_lb": 90_000}, "load_lb", "INVALID_INPUT"),
        ({"load_lb": "heavy"}, "load_lb", "INVALID_INPUT"),
        ({"interval_mi": 30}, "interval_mi", "INVALID_INPUT"),
        ({"departure": "tomorrow"}, "departure", "INVALID_INPUT"),
        ({"destination": {"label": "Same", "lat": 35.0001, "lon": -97.0}}, "destination", "SAME_PLACE"),
        ({"origin": {"label": "x", "lat": 95, "lon": 0}}, "origin", "INVALID_INPUT"),
    ],
)
def test_validation_errors(client, body, monkeypatch, patch, field, code):
    monkeypatch.setattr(services, "get_router", lambda: FakeRouter())
    monkeypatch.setattr(services, "fetch_hourly", fake_weather())
    body.update(patch)
    r = client.post("/api/plan", body, format="json")
    assert r.status_code == 400, r.content
    err = r.json()["error"]
    assert err["code"] == code and err["field"] == field
    assert err["message"] and not err["message"].startswith("This field")


def test_missing_fields_have_friendly_messages(client):
    r = client.post("/api/plan", {}, format="json")
    assert r.status_code == 400
    assert r.json()["error"]["message"] == "Choose a starting point from the list."


def test_upstream_failure_is_503_with_message(client, body, monkeypatch):
    monkeypatch.setattr(services, "get_router", lambda: FakeRouter())

    def boom(*a, **k):
        raise UpstreamError("WEATHER_UNAVAILABLE", "The weather service is unavailable right now. Try again in a minute.")

    monkeypatch.setattr(services, "fetch_hourly", boom)
    r = client.post("/api/plan", body, format="json")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "WEATHER_UNAVAILABLE"


def test_heatmap_shape(client, monkeypatch):
    monkeypatch.setattr(services, "fetch_hourly", fake_weather(wind=40.0))
    line = [[-97.0, 35.0], [-97.0, 36.0], [-96.5, 37.0]]
    dep = datetime.now(timezone.utc) + timedelta(hours=1)
    r = client.post("/api/heatmap", {"lines": [line], "departure": dep.isoformat(), "load_lb": 45_000}, format="json")
    assert r.status_code == 200, r.content
    data = r.json()
    assert len(data["hours"]) == 49
    assert 0 < len(data["cells"]) <= services.MAX_CELLS
    cell = data["cells"][0]
    assert len(cell["risk"]) == 49
    assert cell["risk"][0] == 3  # 40 mph + 45,000 lb -> Severe


def test_geocode_short_query_returns_nothing(client):
    assert client.get("/api/geocode?q=ab").json() == {"results": []}


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"
