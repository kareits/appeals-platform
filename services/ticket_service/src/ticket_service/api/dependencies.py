"""FastAPI dependencies for the ticket API.

Provides a request-scoped database session (the unit of work) and the registration-number
allocator. Route handlers commit explicitly on success; the session context rolls back and closes
on any error, so a failed request never persists a partial change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ticket_service.infrastructure.registration import RegistrationNumberAllocator


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async session.

    The session is closed when the request finishes; because handlers commit explicitly, an
    uncommitted session (after an error) is rolled back on close.

    Args:
        request: The incoming request, used to reach the app's session factory.

    Yields:
        An open async session.
    """
    async with request.app.state.session_factory() as session:
        yield session


def get_allocator(request: Request) -> RegistrationNumberAllocator:
    """Return the registration-number allocator held on the application state.

    Args:
        request: The incoming request.

    Returns:
        The shared allocator.
    """
    allocator: RegistrationNumberAllocator = request.app.state.registration_allocator
    return allocator
