"""Workspace-aggregation tests for the BFF gateway."""

from __future__ import annotations

import uuid

import httpx
from bff_fakes import ClientFactory, Handler, auth_me_handler, new_ticket_id


def _ticket_handler(
    ticket_id: uuid.UUID, *, card_status: int = 200, comments_mode: str = "ok"
) -> Handler:
    """Build a fake Ticket Service handler for the workspace reads.

    Args:
        ticket_id: The appeal whose card and comments are served.
        card_status: The status code returned for the card read.
        comments_mode: ``"ok"`` returns an empty comment list, ``"fail"`` raises a transport error.

    Returns:
        A mock-transport handler for the fake Ticket Service.
    """
    card_path = f"/api/v1/tickets/{ticket_id}"
    comments_path = f"{card_path}/comments"

    def _handler(request: httpx.Request) -> httpx.Response:
        """Serve the fake card and comments reads.

        Args:
            request: The incoming request.

        Returns:
            The simulated Ticket Service response.

        Raises:
            httpx.ConnectError: When the comments read is configured to fail.
        """
        if request.url.path == comments_path:
            if comments_mode == "fail":
                raise httpx.ConnectError("connection refused", request=request)
            return httpx.Response(200, json=[])
        if request.url.path == card_path:
            if card_status == 404:
                return httpx.Response(404, json={"title": "Ticket not found", "status": 404})
            return httpx.Response(200, json={"id": str(ticket_id), "statusCode": "NEW"})
        return httpx.Response(404, json={"title": "Not found", "status": 404})

    return _handler


async def test_workspace_aggregates_card_and_comments(build_client: ClientFactory) -> None:
    """A healthy read returns ok sections, not-implemented placeholders, and degraded=false."""
    ticket_id = new_ticket_id()
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_ticket_handler(ticket_id),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticketId"] == str(ticket_id)
    assert body["degraded"] is False
    sections = body["sections"]
    assert sections["ticket"]["status"] == "ok"
    assert sections["ticket"]["data"]["id"] == str(ticket_id)
    assert sections["comments"]["status"] == "ok"
    assert sections["comments"]["data"] == []
    for placeholder in ("process", "mail", "documents"):
        assert sections[placeholder]["status"] == "not_implemented"
        assert sections[placeholder]["data"] is None


async def test_workspace_missing_ticket_is_404(build_client: ClientFactory) -> None:
    """A missing appeal (Ticket Service 404) makes the whole workspace a 404."""
    ticket_id = new_ticket_id()
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_ticket_handler(ticket_id, card_status=404),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_workspace_flags_partial_failure(build_client: ClientFactory) -> None:
    """A failed comments read degrades the workspace but still returns the card at 200."""
    ticket_id = new_ticket_id()
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_ticket_handler(ticket_id, comments_mode="fail"),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert body["sections"]["ticket"]["status"] == "ok"
    assert body["sections"]["comments"]["status"] == "unavailable"
    assert body["sections"]["comments"]["data"] is None


def _card_handler(
    ticket_id: uuid.UUID, *, card_status: int, mode: str = "json", comments_status: int = 200
) -> Handler:
    """Build a fake Ticket handler returning a chosen card status/mode and comments status.

    Args:
        ticket_id: The appeal whose reads are served.
        card_status: The status returned for the card read.
        mode: ``"json"`` (valid body), ``"malformed"`` (invalid JSON), or ``"timeout"``.
        comments_status: The status returned for the comments read.

    Returns:
        A mock-transport handler.
    """
    card_path = f"/api/v1/tickets/{ticket_id}"
    comments_path = f"{card_path}/comments"

    def _handler(request: httpx.Request) -> httpx.Response:
        """Serve the configured card and comments responses.

        Args:
            request: The incoming request.

        Returns:
            The simulated response.

        Raises:
            httpx.ReadTimeout: When the card read is configured to time out.
        """
        if request.url.path == comments_path:
            return httpx.Response(comments_status, json=[])
        if mode == "timeout":
            raise httpx.ReadTimeout("card timed out", request=request)
        if mode == "malformed":
            return httpx.Response(
                card_status, content=b"not json", headers={"content-type": "application/json"}
            )
        return httpx.Response(card_status, json={"id": str(ticket_id)})

    return _handler


async def test_workspace_card_401_propagates(build_client: ClientFactory) -> None:
    """A downstream 401 on the card is surfaced as a request-level 401, not a masked 200."""
    ticket_id = new_ticket_id()
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_handler(ticket_id, card_status=401),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_workspace_card_403_propagates(build_client: ClientFactory) -> None:
    """A downstream 403 on the card is surfaced as a request-level 403, not a masked 200."""
    ticket_id = new_ticket_id()
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_handler(ticket_id, card_status=403),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 403


async def test_workspace_comments_403_propagates(build_client: ClientFactory) -> None:
    """A downstream 403 on comments is a critical auth failure, surfaced as 403 (not degraded)."""
    ticket_id = new_ticket_id()
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_handler(ticket_id, card_status=200, comments_status=403),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 403


async def test_workspace_card_timeout_is_504(build_client: ClientFactory) -> None:
    """A card read timeout maps to a gateway 504, never a masked 200."""
    ticket_id = new_ticket_id()
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_handler(ticket_id, card_status=200, mode="timeout"),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 504


async def test_workspace_card_5xx_is_502(build_client: ClientFactory) -> None:
    """A card 5xx maps to a safe gateway 502, without leaking the downstream body."""
    ticket_id = new_ticket_id()
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_handler(ticket_id, card_status=500),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 502


async def test_workspace_card_malformed_json_is_502(build_client: ClientFactory) -> None:
    """A malformed card JSON body maps to a gateway 502, not an unhandled 500."""
    ticket_id = new_ticket_id()
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_handler(ticket_id, card_status=200, mode="malformed"),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 502


def _card_media_handler(ticket_id: uuid.UUID, *, card: httpx.Response) -> Handler:
    """Build a Ticket handler returning a chosen card response and an empty comments list.

    Args:
        ticket_id: The appeal whose reads are served.
        card: The exact response to return for the card read.

    Returns:
        A mock-transport handler.
    """
    card_path = f"/api/v1/tickets/{ticket_id}"

    def _handler(request: httpx.Request) -> httpx.Response:
        """Serve the configured card response and an empty comments list.

        Args:
            request: The incoming request.

        Returns:
            The simulated response.
        """
        if request.url.path == f"{card_path}/comments":
            return httpx.Response(200, json=[])
        return card

    return _handler


async def test_workspace_card_wrong_media_type_is_502(build_client: ClientFactory) -> None:
    """A card 200 with a non-JSON media type (even if the body is JSON) maps to a safe 502."""
    ticket_id = new_ticket_id()
    card = httpx.Response(200, content=b'{"id": "x"}', headers={"content-type": "text/plain"})
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_media_handler(ticket_id, card=card),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 502


async def test_workspace_card_wrong_shape_is_502(build_client: ClientFactory) -> None:
    """A card 200 whose JSON is not the minimal card object envelope maps to a safe 502."""
    ticket_id = new_ticket_id()
    card = httpx.Response(200, json=[1, 2, 3])  # a JSON array, not a card object
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_media_handler(ticket_id, card=card),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 502


async def test_workspace_comments_wrong_media_degrades(build_client: ClientFactory) -> None:
    """A comments 200 with an unexpected media type degrades the optional section (200 degraded)."""
    ticket_id = new_ticket_id()
    card_path = f"/api/v1/tickets/{ticket_id}"

    def _handler(request: httpx.Request) -> httpx.Response:
        """Return a valid card but comments with a wrong media type.

        Args:
            request: The incoming request.

        Returns:
            The simulated response.
        """
        if request.url.path == f"{card_path}/comments":
            return httpx.Response(200, content=b"[]", headers={"content-type": "text/plain"})
        return httpx.Response(200, json={"id": str(ticket_id)})

    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)), ticket_handler=_handler
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert body["sections"]["comments"]["status"] == "unavailable"
    assert body["sections"]["ticket"]["status"] == "ok"


async def test_workspace_oversized_card_is_502(build_client: ClientFactory) -> None:
    """An oversized card body is treated as a protocol failure (502), not trusted data."""
    ticket_id = new_ticket_id()
    big = b'{"id": "' + b"x" * 2_100_000 + b'"}'
    card = httpx.Response(200, content=big, headers={"content-type": "application/json"})
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_media_handler(ticket_id, card=card),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 502


def _comments_handler(ticket_id: uuid.UUID, *, comments: httpx.Response) -> Handler:
    """Build a Ticket handler returning a valid card and a chosen comments response.

    Args:
        ticket_id: The appeal whose reads are served.
        comments: The exact response to return for the comments read.

    Returns:
        A mock-transport handler.
    """
    card_path = f"/api/v1/tickets/{ticket_id}"

    def _handler(request: httpx.Request) -> httpx.Response:
        """Serve a valid card and the configured comments response.

        Args:
            request: The incoming request.

        Returns:
            The simulated response.
        """
        if request.url.path == f"{card_path}/comments":
            return comments
        return httpx.Response(200, json={"id": str(ticket_id)})

    return _handler


async def test_workspace_card_jsonp_media_type_is_502(build_client: ClientFactory) -> None:
    """A card advertised as application/jsonp is rejected (exact media-type parsing)."""
    ticket_id = new_ticket_id()
    card = httpx.Response(
        200, content=b'{"id": "x"}', headers={"content-type": "application/jsonp"}
    )
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_media_handler(ticket_id, card=card),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 502


async def test_workspace_card_nested_json_media_type_is_502(build_client: ClientFactory) -> None:
    """A card advertised as text/application/json is rejected (exact media-type parsing)."""
    ticket_id = new_ticket_id()
    card = httpx.Response(
        200, content=b'{"id": "x"}', headers={"content-type": "text/application/json"}
    )
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_media_handler(ticket_id, card=card),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 502


async def test_workspace_card_invalid_utf8_is_502(build_client: ClientFactory) -> None:
    """A card body that is not valid UTF-8 JSON maps to a safe 502."""
    ticket_id = new_ticket_id()
    card = httpx.Response(
        200, content=b"\xff\xfe\x00", headers={"content-type": "application/json"}
    )
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_card_media_handler(ticket_id, card=card),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 502


async def test_workspace_oversized_comments_degrade(build_client: ClientFactory) -> None:
    """An oversized comments body is not fully buffered; the optional section degrades."""
    ticket_id = new_ticket_id()
    big = b'[{"id": "' + b"x" * 2_100_000 + b'"}]'
    comments = httpx.Response(200, content=big, headers={"content-type": "application/json"})
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_comments_handler(ticket_id, comments=comments),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert body["sections"]["comments"]["status"] == "unavailable"


async def test_workspace_invalid_comment_items_degrade(build_client: ClientFactory) -> None:
    """Comments lists with primitive or envelope-less items are not marked ok."""
    ticket_id = new_ticket_id()
    for payload in (b"[123]", b"[null]", b'[{"unexpected": "value"}]'):
        comments = httpx.Response(
            200, content=payload, headers={"content-type": "application/json"}
        )
        client = await build_client(
            iam_handler=auth_me_handler(("ticket:read",)),
            ticket_handler=_comments_handler(ticket_id, comments=comments),
        )
        response = await client.get(
            f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
        )
        assert response.status_code == 200, payload
        assert response.json()["sections"]["comments"]["status"] == "unavailable", payload


async def test_workspace_valid_comment_items_are_ok(build_client: ClientFactory) -> None:
    """A comments list of well-formed comment objects is returned as ok."""
    ticket_id = new_ticket_id()
    comments = httpx.Response(200, json=[{"id": "c1", "body": "hi"}, {"id": "c2", "body": "yo"}])
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_comments_handler(ticket_id, comments=comments),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is False
    assert body["sections"]["comments"]["status"] == "ok"
    assert len(body["sections"]["comments"]["data"]) == 2


async def test_workspace_requires_read_permission(build_client: ClientFactory) -> None:
    """A caller without ticket:read is rejected at the gateway with 403."""
    ticket_id = new_ticket_id()
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:create",)),
        ticket_handler=_ticket_handler(ticket_id),
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}/workspace", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 403
