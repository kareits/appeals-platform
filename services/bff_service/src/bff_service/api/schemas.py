"""Response schemas for the BFF API and mappers from application results.

Only the gateway-owned response shapes are modelled here: the resolved auth context and the
aggregated workspace envelope. Ticket command and search bodies are forwarded verbatim to the Ticket
Service and are not re-modelled (BFF_SERVICE spec: do not duplicate domain logic). Fields serialize
as camelCase to match the API conventions (docs/05).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from bff_service.application.auth_context import AuthContext
from bff_service.application.workspace import Section, SectionStatus, Workspace


class ResponseModel(BaseModel):
    """Base response model serializing fields as camelCase.

    ``populate_by_name`` lets mappers construct instances using the Python field names while the API
    still emits the camelCase aliases.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AuthContextResponse(ResponseModel):
    """The caller's resolved auth context.

    Attributes:
        subject: The subject's identifier.
        username: The subject's login handle.
        roles: The subject's granted roles.
        permissions: The subject's resolved permission claims.
    """

    subject: uuid.UUID
    username: str
    roles: list[str]
    permissions: list[str]


class WorkspaceSectionResponse(ResponseModel):
    """A single workspace section.

    Attributes:
        status: The read status of the section.
        data: The section payload when ``status`` is ``ok``; ``None`` otherwise. Always present in
            the response (``null`` when there is no payload), so it is a required field.
    """

    status: SectionStatus
    data: Any


class WorkspaceSectionsResponse(ResponseModel):
    """The workspace sections aggregated for the appeal.

    Attributes:
        ticket: The appeal card section.
        comments: The appeal comments section.
        process: The process section (placeholder in EP-1).
        mail: The mail-timeline section (placeholder in EP-1).
        documents: The documents section (placeholder in EP-1).
    """

    ticket: WorkspaceSectionResponse
    comments: WorkspaceSectionResponse
    process: WorkspaceSectionResponse
    mail: WorkspaceSectionResponse
    documents: WorkspaceSectionResponse


class WorkspaceResponse(ResponseModel):
    """The aggregated appeal workspace.

    Attributes:
        ticket_id: The appeal identifier.
        degraded: ``True`` when at least one section could not be read (partial failure).
        sections: The aggregated sections.
    """

    ticket_id: uuid.UUID
    degraded: bool
    sections: WorkspaceSectionsResponse


def auth_context_to_response(context: AuthContext) -> AuthContextResponse:
    """Map an :class:`AuthContext` to its response model.

    Args:
        context: The resolved auth context.

    Returns:
        The response model.
    """
    return AuthContextResponse(
        subject=context.subject,
        username=context.username,
        roles=list(context.roles),
        permissions=sorted(context.permissions),
    )


def _section_to_response(section: Section) -> WorkspaceSectionResponse:
    """Map an aggregated section to its response model.

    Args:
        section: The aggregated section.

    Returns:
        The response model.
    """
    return WorkspaceSectionResponse(status=section.status, data=section.data)


def workspace_to_response(workspace: Workspace) -> WorkspaceResponse:
    """Map an aggregated :class:`Workspace` to its response model.

    Args:
        workspace: The aggregated workspace.

    Returns:
        The response model.
    """
    return WorkspaceResponse(
        ticket_id=workspace.ticket_id,
        degraded=workspace.degraded,
        sections=WorkspaceSectionsResponse(
            ticket=_section_to_response(workspace.ticket),
            comments=_section_to_response(workspace.comments),
            process=_section_to_response(workspace.process),
            mail=_section_to_response(workspace.mail),
            documents=_section_to_response(workspace.documents),
        ),
    )
