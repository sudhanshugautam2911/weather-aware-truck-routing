"""Turn any unexpected server error into a calm, consistent JSON message."""

import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler

log = logging.getLogger(__name__)


def handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        code = getattr(exc, "default_code", "error").upper()
        message = str(detail) if detail else "The request could not be processed."
        if code == "THROTTLED":
            message = "Too many trips planned in a short time. Wait a minute and try again."
        response.data = {"error": {"code": code, "message": message}}
        return response
    log.exception("unhandled error", exc_info=exc)
    return Response(
        {"error": {"code": "SERVER_ERROR", "message": "Something went wrong on our side. Try again in a moment."}},
        status=500,
    )
