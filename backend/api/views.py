import logging

from django.conf import settings
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from core.errors import AppError
from providers.geocoding import search_places
from providers.routing import get_router

from . import services
from .serializers import HeatmapRequestSerializer, PlanRequestSerializer

log = logging.getLogger(__name__)


class PlanThrottle(AnonRateThrottle):
    rate = "30/min"


def _error(exc: AppError) -> Response:
    return Response({"error": exc.as_dict()}, status=exc.status)


def _validation_error(errors: dict) -> Response:
    """First field error, flattened into the same shape as AppError."""
    field, messages = next(iter(errors.items()))
    while isinstance(messages, dict):
        field, messages = next(iter(messages.items()))
    message = messages[0] if isinstance(messages, list) and messages else str(messages)
    if isinstance(message, dict):
        message = next(iter(message.values()))[0]
    field_map = {"lat": "place", "lon": "place", "label": "place"}
    return Response(
        {"error": {"code": "INVALID_INPUT", "message": str(message), "field": field_map.get(field, field)}},
        status=400,
    )


@api_view(["GET"])
def health(request):
    router = get_router()
    return Response(
        {
            "status": "ok",
            "routing_provider": router.name,
            "truck_aware": router.truck_aware,
            "geocoder": "tomtom" if settings.TOMTOM_API_KEY else "photon-demo",
        }
    )


@api_view(["GET"])
def geocode(request):
    q = (request.query_params.get("q") or "").strip()
    if len(q) < 3:
        return Response({"results": []})
    if len(q) > 200:
        return _error(AppError("INVALID_INPUT", "That search is too long. Shorten it and try again.", field="q"))
    try:
        places = search_places(q)
    except AppError as exc:
        return _error(exc)
    return Response({"results": [p.as_dict() for p in places]})


@api_view(["POST"])
@throttle_classes([PlanThrottle])
def plan(request):
    ser = PlanRequestSerializer(data=request.data)
    if not ser.is_valid():
        resp = _validation_error(ser.errors)
        if "origin" in ser.errors:
            resp.data["error"]["field"] = "origin"
        elif "destination" in ser.errors:
            resp.data["error"]["field"] = "destination"
        return resp
    d = ser.validated_data
    try:
        result = services.plan_trip(
            services.Place(**d["origin"]),
            services.Place(**d["destination"]),
            d["departure"],
            d["load_lb"],
            int(d["interval_mi"]),
        )
    except AppError as exc:
        return _error(exc)
    return Response(result)


@api_view(["POST"])
@throttle_classes([PlanThrottle])
def heatmap(request):
    ser = HeatmapRequestSerializer(data=request.data)
    if not ser.is_valid():
        return _validation_error(ser.errors)
    d = ser.validated_data
    try:
        lines = [[(p[0], p[1]) for p in line] for line in d["lines"]]
        result = services.build_heatmap(lines, d["departure"], d["load_lb"])
    except AppError as exc:
        return _error(exc)
    return Response(result)
