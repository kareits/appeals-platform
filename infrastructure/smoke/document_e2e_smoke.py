"""Authenticated end-to-end smoke check for the Document Service (TASK_03A-1).

Run from inside the compose network, because the document service publishes no host port:

    docker run --rm --network appeals-platform_backend -v "$PWD/infrastructure/smoke:/smoke:ro" \
        python:3.12-slim python /smoke/document_e2e_smoke.py \
        http://document_service:8000 http://iam_service:8000 http://ticket_service:8000

It exercises the real trust boundary across services — not mocks — so the compose smoke fails
unless the acceptance path works and the key security negatives hold:

- a real IAM-issued token is accepted, an upload is stored, listed, and downloaded byte-for-byte;
- the download is served as an untyped attachment with nosniff, so untrusted content is never
  rendered;
- an unauthenticated request is refused with 401 even though the service sits behind the gateway;
- a caller without appeal permissions is refused with 403;
- a caller outside the appeal's scope is refused with 403 — the object-level decision delegated to
  the Ticket Service (ADR-0012, CR-DOC-HIGH-001) really runs across the service boundary;
- a **composite role** that may read an appeal but not modify it (EMPLOYEE + AUDITOR on another
  team's appeal) is refused with 403 on upload and link while still being able to read, proving the
  write path asks Ticket's narrower mutation decision (CR-DOC-HIGH-002);
- linking a stored document to a second, reachable appeal is refused with 409 (write-once
  evidence).

The appeals used by a run are registered through the Ticket Service with fixed idempotency keys, so
re-running — including the post-restart verification pass — reuses the same appeals instead of
creating new ones, and no state has to be carried between container invocations.

Uses only the standard library so it needs no dependencies in the CI runner.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid

_DEV_PASSWORD = "changeme-dev-01"
_BOUNDARY = "----documentsmokeboundary"
_CONTENT = b"%PDF-1.4 compose smoke evidence"

# Fixed so the full run and the post-restart verification target the same appeal.
_APPEAL_IDEMPOTENCY_KEY = "document-e2e-smoke-appeal"
_SECOND_APPEAL_IDEMPOTENCY_KEY = "document-e2e-smoke-appeal-2"


def _request(
    url: str,
    method: str,
    *,
    token: str | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    """Perform an HTTP request and return the status, raw body, and headers.

    Args:
        url: The absolute request URL.
        method: The HTTP method.
        token: Optional bearer token.
        body: Optional raw request body.
        content_type: Optional request content type.
        extra_headers: Optional additional request headers.

    Returns:
        A tuple of status code, raw response body, and lower-cased response headers.
    """
    request = urllib.request.Request(url, data=body, method=method)
    if content_type is not None:
        request.add_header("Content-Type", content_type)
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    for name, value in (extra_headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request) as response:
            headers = {name.lower(): value for name, value in response.headers.items()}
            return response.status, response.read(), headers
    except urllib.error.HTTPError as error:
        headers = {name.lower(): value for name, value in error.headers.items()}
        return error.code, error.read(), headers


def _json(raw: bytes) -> dict:
    """Decode a JSON response body, tolerating an empty or non-JSON body.

    Args:
        raw: The raw response bytes.

    Returns:
        The decoded object, or an empty dict.
    """
    try:
        value = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _login(iam_url: str, username: str) -> str:
    """Log in against IAM and return the access token.

    Args:
        iam_url: The IAM service base URL on the compose network.
        username: The dev username.

    Returns:
        The access token.

    Raises:
        AssertionError: If login does not return a token.
    """
    payload = json.dumps({"username": username, "password": _DEV_PASSWORD}).encode("utf-8")
    status, raw, _ = _request(
        f"{iam_url}/api/v1/auth/login", "POST", body=payload, content_type="application/json"
    )
    assert status == 200, f"login {username}: expected 200, got {status} {raw!r}"
    token = _json(raw).get("accessToken")
    assert isinstance(token, str) and token, f"login {username}: no access token"
    return token


def _register_appeal(ticket_url: str, token: str, *, idempotency_key: str, subject: str) -> str:
    """Register (or reuse) an appeal the document run can attach evidence to.

    A fixed idempotency key and a fixed payload make the call re-runnable: the Ticket Service
    returns the original appeal on a replay, so the post-restart verification pass targets the same
    appeal without any state carried between container invocations.

    Args:
        ticket_url: The Ticket Service base URL on the compose network.
        token: A bearer token holding the appeal-registration permission.
        idempotency_key: The fixed key identifying this smoke appeal.
        subject: The appeal subject, kept stable so a replay has an identical payload.

    Returns:
        The appeal identifier.

    Raises:
        AssertionError: If the appeal could not be registered or replayed.
    """
    payload = json.dumps(
        {
            "receivedAt": "2026-08-12T09:00:00Z",
            "sourceChannelCode": "EMAIL",
            "subject": subject,
            "description": "Created by the document compose E2E smoke.",
            "productCode": "MICROLOAN",
            "classifierCode": "RESTRUCTURING",
            "priorityCode": "NORMAL",
            "applicant": {"applicantType": "CONSUMER", "dataSource": "MANUAL", "fullName": "E2E"},
        }
    ).encode("utf-8")
    status, raw, _ = _request(
        f"{ticket_url}/api/v1/tickets",
        "POST",
        token=token,
        body=payload,
        content_type="application/json",
        extra_headers={"Idempotency-Key": idempotency_key},
    )
    assert status in {200, 201}, f"register appeal: expected 200/201, got {status} {raw!r}"
    appeal_id = _json(raw).get("id")
    assert isinstance(appeal_id, str) and appeal_id, "register appeal: no identifier returned"
    return appeal_id


def _multipart(filename: str, content: bytes, fields: dict[str, str]) -> bytes:
    """Build a multipart/form-data body carrying one file part and simple text fields.

    Args:
        filename: The filename declared for the file part.
        content: The file bytes.
        fields: Additional text fields.

    Returns:
        The encoded multipart body.
    """
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{_BOUNDARY}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode()
        )
    parts.append(
        f'--{_BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n".encode()
    )
    parts.append(content)
    parts.append(f"\r\n--{_BOUNDARY}--\r\n".encode())
    return b"".join(parts)


def _upload(document_url: str, token: str, ticket_id: str) -> dict:
    """Upload a document linked to an appeal and return its metadata.

    Args:
        document_url: The document service base URL.
        token: A bearer token holding the write permission.
        ticket_id: The appeal identifier to link to.

    Returns:
        The stored document metadata.

    Raises:
        AssertionError: If the upload is not accepted.
    """
    body = _multipart("evidence.pdf", _CONTENT, {"ticketId": ticket_id})
    status, raw, _ = _request(
        f"{document_url}/api/v1/documents",
        "POST",
        token=token,
        body=body,
        content_type=f"multipart/form-data; boundary={_BOUNDARY}",
    )
    assert status == 201, f"upload: expected 201, got {status} {raw!r}"
    document = _json(raw)
    assert document["status"] == "AVAILABLE", f"upload: unexpected status {document['status']}"
    assert document["ticketId"] == ticket_id, "upload: the appeal linkage was not recorded"
    assert "storageKey" not in document, "upload: the internal storage key must not be exposed"
    return document


def _check_round_trip(document_url: str, token: str, ticket_id: str, document: dict) -> None:
    """Assert that the uploaded document is listed and downloaded intact and safely.

    Args:
        document_url: The document service base URL.
        token: A bearer token holding the read permission.
        ticket_id: The appeal the document is linked to.
        document: The uploaded document metadata.

    Raises:
        AssertionError: If listing, download, or the response hardening fails.
    """
    status, raw, _ = _request(
        f"{document_url}/api/v1/documents?ticketId={ticket_id}", "GET", token=token
    )
    assert status == 200, f"list: expected 200, got {status}"
    listed = _json(raw)
    assert [item["id"] for item in listed["items"]] == [document["id"]], "list: wrong contents"

    status, raw, headers = _request(
        f"{document_url}/api/v1/documents/{document['id']}/content", "GET", token=token
    )
    assert status == 200, f"download: expected 200, got {status}"
    assert raw == _CONTENT, "download: the content did not survive the round trip"
    assert headers["content-type"] == "application/octet-stream", "download: renderable media type"
    assert headers["content-disposition"].startswith("attachment;"), "download: not an attachment"
    assert headers["x-content-type-options"] == "nosniff", "download: missing nosniff"


def _check_negatives(document_url: str, document_id: str, admin_token: str) -> None:
    """Assert the permission-level security negatives on the direct service boundary.

    Args:
        document_url: The document service base URL.
        document_id: An existing document identifier.
        admin_token: A token for a caller holding no appeal permissions.

    Raises:
        AssertionError: If an unauthorized request is not refused.
    """
    status, _, headers = _request(f"{document_url}/api/v1/documents/{document_id}", "GET")
    assert status == 401, f"unauthenticated read: expected 401, got {status}"
    assert headers.get("www-authenticate") == "Bearer", "401 without a bearer challenge"

    status, _, _ = _request(
        f"{document_url}/api/v1/documents/{document_id}", "GET", token=admin_token
    )
    assert status == 403, f"caller without appeal permissions: expected 403, got {status}"


def _check_appeal_scope_enforced(document_url: str, token: str) -> None:
    """Assert that object-level appeal scope is enforced across the real service boundary.

    Regression check for CR-DOC-HIGH-001: holding ``ticket:read`` is not enough. An appeal the
    caller cannot reach — here an identifier the Ticket Service does not know — must yield 403 on
    both listing and upload, never a page or a stored document.

    Args:
        document_url: The document service base URL.
        token: A bearer token holding the read and write permissions.

    Raises:
        AssertionError: If an out-of-scope appeal is served or accepted.
    """
    stranger = str(uuid.uuid4())

    status, _, _ = _request(
        f"{document_url}/api/v1/documents?ticketId={stranger}", "GET", token=token
    )
    assert status == 403, f"list of an out-of-scope appeal: expected 403, got {status}"

    body = _multipart("evidence.pdf", _CONTENT, {"ticketId": stranger})
    status, _, _ = _request(
        f"{document_url}/api/v1/documents",
        "POST",
        token=token,
        body=body,
        content_type=f"multipart/form-data; boundary={_BOUNDARY}",
    )
    assert status == 403, f"upload to an out-of-scope appeal: expected 403, got {status}"


def _check_relink_refused(document_url: str, token: str, document_id: str, appeal_id: str) -> None:
    """Assert that stored evidence is not moved between appeals.

    The destination is a second, genuinely reachable appeal, so the refusal proves the write-once
    rule rather than merely repeating the scope check.

    Args:
        document_url: The document service base URL.
        token: A bearer token holding the write permission.
        document_id: The document already linked to another appeal.
        appeal_id: The reachable destination appeal.

    Raises:
        AssertionError: If the conflicting link is accepted.
    """
    payload = json.dumps({"ticketId": appeal_id}).encode("utf-8")
    status, _, _ = _request(
        f"{document_url}/api/v1/documents/{document_id}/link",
        "POST",
        token=token,
        body=payload,
        content_type="application/json",
    )
    assert status == 409, f"relink to another appeal: expected 409, got {status}"


def _grant_role(iam_url: str, admin_token: str, username: str, role: str) -> str:
    """Grant a role to a seeded dev user and return the user identifier.

    Used to build the composite grant the escalation check needs, because the seeded dev users hold
    exactly one role each. The caller is expected to revoke it again.

    Args:
        iam_url: The IAM service base URL.
        admin_token: A token holding ``iam:manage``.
        username: The dev user to modify.
        role: The role to add.

    Returns:
        The user's identifier.

    Raises:
        AssertionError: If the user cannot be resolved or the grant is refused.
    """
    status, raw, _ = _request(f"{iam_url}/api/v1/auth/me", "GET", token=_login(iam_url, username))
    assert status == 200, f"resolve {username}: expected 200, got {status} {raw!r}"
    user_id = _json(raw).get("subject")
    assert isinstance(user_id, str) and user_id, f"resolve {username}: no subject"

    status, raw, _ = _request(
        f"{iam_url}/api/v1/users/{user_id}/roles",
        "POST",
        token=admin_token,
        body=json.dumps({"role": role}).encode("utf-8"),
        content_type="application/json",
    )
    assert status in {200, 201, 204}, f"grant {role}: expected 2xx, got {status} {raw!r}"
    return user_id


def _revoke_role(iam_url: str, admin_token: str, user_id: str, role: str) -> None:
    """Revoke a role again, leaving the seeded dev users as the migration created them.

    Args:
        iam_url: The IAM service base URL.
        admin_token: A token holding ``iam:manage``.
        user_id: The user to modify.
        role: The role to remove.
    """
    status, raw, _ = _request(
        f"{iam_url}/api/v1/users/{user_id}/roles/{role}", "DELETE", token=admin_token
    )
    assert status in {200, 204}, f"revoke {role}: expected 2xx, got {status} {raw!r}"


def _check_composite_role_cannot_write(
    document_url: str, iam_url: str, ticket_url: str, admin_token: str, appeal_id: str
) -> None:
    """Assert that read scope borrowed from an audit role cannot authorize an evidence write.

    Grants AUDITOR to the seeded `employee` user, so that caller holds EMPLOYEE's ``ticket:update``
    permission *and* AUDITOR's organization-wide read scope. Ticket lets them read the supervisor's
    appeal but refuses to let them modify it, so the document service must refuse the upload and the
    link while still serving the read (CR-DOC-HIGH-002). The grant is always revoked afterwards.

    Args:
        document_url: The document service base URL.
        iam_url: The IAM service base URL.
        ticket_url: The Ticket Service base URL.
        admin_token: A token holding ``iam:manage``.
        appeal_id: An appeal registered by another user (the supervisor).

    Raises:
        AssertionError: If the composite caller can write, or cannot read.
    """
    user_id = _grant_role(iam_url, admin_token, "employee", "AUDITOR")
    try:
        composite = _login(iam_url, "employee")

        status, raw, _ = _request(
            f"{ticket_url}/api/v1/tickets/{appeal_id}", "GET", token=composite
        )
        assert status == 200, f"composite read of the appeal: expected 200, got {status} {raw!r}"
        status, raw, _ = _request(
            f"{ticket_url}/api/v1/tickets/{appeal_id}/access", "GET", token=composite
        )
        assert status == 200, f"access probe: expected 200, got {status}"
        decision = _json(raw)
        assert decision["canRead"] is True, "composite caller should be able to read the appeal"
        assert decision["canMutate"] is False, "composite caller must not be able to mutate it"

        body = _multipart("smuggled.pdf", _CONTENT, {"ticketId": appeal_id})
        status, _, _ = _request(
            f"{document_url}/api/v1/documents",
            "POST",
            token=composite,
            body=body,
            content_type=f"multipart/form-data; boundary={_BOUNDARY}",
        )
        assert status == 403, f"composite upload: expected 403, got {status}"

        status, raw, _ = _request(
            f"{document_url}/api/v1/documents?ticketId={appeal_id}", "GET", token=composite
        )
        assert status == 200, f"composite list: expected 200 (read is allowed), got {status}"
        items = _json(raw)["items"]
        assert items, "the earlier upload should still be listed"

        unlinked = _multipart("own.pdf", _CONTENT, {})
        status, raw, _ = _request(
            f"{document_url}/api/v1/documents",
            "POST",
            token=composite,
            body=unlinked,
            content_type=f"multipart/form-data; boundary={_BOUNDARY}",
        )
        assert status == 201, f"composite unlinked upload: expected 201, got {status} {raw!r}"
        own_document = _json(raw)["id"]
        status, _, _ = _request(
            f"{document_url}/api/v1/documents/{own_document}/link",
            "POST",
            token=composite,
            body=json.dumps({"ticketId": appeal_id}).encode("utf-8"),
            content_type="application/json",
        )
        assert status == 403, f"composite link: expected 403, got {status}"
    finally:
        _revoke_role(iam_url, admin_token, user_id, "AUDITOR")


def _verify_existing(document_url: str, token: str, ticket_id: str) -> None:
    """Assert that a previously uploaded document is still listed and downloadable.

    Used after a container restart to check the acceptance criterion "restart does not lose files"
    against the real persistent volume rather than a temporary directory.

    Args:
        document_url: The document service base URL.
        token: A bearer token holding the read permission.
        ticket_id: The appeal whose document was uploaded before the restart.

    Raises:
        AssertionError: If the document or its bytes did not survive.
    """
    status, raw, _ = _request(
        f"{document_url}/api/v1/documents?ticketId={ticket_id}", "GET", token=token
    )
    assert status == 200, f"verify: list expected 200, got {status}"
    items = _json(raw)["items"]
    assert len(items) == 1, f"verify: expected exactly one document, got {len(items)}"

    status, content, _ = _request(
        f"{document_url}/api/v1/documents/{items[0]['id']}/content", "GET", token=token
    )
    assert status == 200, f"verify: download expected 200, got {status}"
    assert content == _CONTENT, "verify: the stored bytes did not survive the restart"


def main(argv: list[str]) -> int:
    """Run the document acceptance path, or verify a previous upload after a restart.

    Args:
        argv: Command-line arguments: ``<document-url> <iam-url> <ticket-url> [--verify-only]``.

    Returns:
        Process exit code (0 on success).
    """
    document_url = argv[0] if argv else "http://document_service:8000"
    iam_url = argv[1] if len(argv) > 1 else "http://iam_service:8000"
    ticket_url = argv[2] if len(argv) > 2 else "http://ticket_service:8000"
    verify_only = "--verify-only" in argv

    supervisor = _login(iam_url, "supervisor")
    appeal_id = _register_appeal(
        ticket_url,
        supervisor,
        idempotency_key=_APPEAL_IDEMPOTENCY_KEY,
        subject="Document E2E smoke appeal",
    )

    if verify_only:
        _verify_existing(document_url, supervisor, appeal_id)
        print(f"Document persistence verified after restart for appeal {appeal_id}")
        return 0

    second_appeal_id = _register_appeal(
        ticket_url,
        supervisor,
        idempotency_key=_SECOND_APPEAL_IDEMPOTENCY_KEY,
        subject="Document E2E smoke appeal (relink target)",
    )
    admin = _login(iam_url, "admin")

    document = _upload(document_url, supervisor, appeal_id)
    _check_round_trip(document_url, supervisor, appeal_id, document)
    _check_negatives(document_url, document["id"], admin)
    _check_appeal_scope_enforced(document_url, supervisor)
    _check_relink_refused(document_url, supervisor, document["id"], second_appeal_id)
    _check_composite_role_cannot_write(document_url, iam_url, ticket_url, admin, appeal_id)

    print(
        "Document E2E smoke passed: upload/list/download round trip, attachment-only download, "
        "401 without a token, 403 without appeal permissions, 403 outside the appeal scope, "
        "403 for a composite role that may read but not mutate the appeal, and 409 on a "
        f"conflicting link. Document id: {document['id']}, appeal id: {appeal_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
