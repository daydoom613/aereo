"""Cross-cutting request handling: request ids, the last-resort error response, the body limit."""

from __future__ import annotations

import logging
import re
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import problem_response
from app.core.logging import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
# A client-supplied id is written to the logs, so only a plain token is accepted.
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class RequestContextMiddleware:
    """Gives every request an id, and turns an unhandled exception into a 500 that carries it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # The traceback goes to the log, never to the client.
            logger.exception("unhandled error")
            if response_started:
                raise
            response = problem_response(500, "An unexpected error occurred.", scope["path"])
            await response(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)


class UploadSizeLimitMiddleware:
    """Refuses request bodies over the limit without reading them in full.

    The declared Content-Length is checked first. The bytes that actually arrive are counted
    as well, because a chunked upload declares no length.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self._detail = f"The upload is larger than the limit of {max_bytes} bytes."

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_bytes:
            response = problem_response(413, self._detail, scope["path"])
            await response(scope, receive, send)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # An HTTPException is the one error FastAPI lets through while it is
                    # still parsing the request body.
                    raise HTTPException(status_code=413, detail=self._detail)
            return message

        await self.app(scope, counting_receive, send)
