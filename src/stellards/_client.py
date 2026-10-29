"""The StellarDS clients."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any

import httpx

from ._async import resources as aio
from ._core import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    ApiRequest,
    AsyncCore,
    OAuthCredentials,
    ProjectId,
    SyncCore,
    TimeoutTypes,
    TokensCallback,
)
from ._sync import resources as sync

__all__ = ["StellarDS", "AsyncStellarDS"]


def _ping_text(data: Any) -> str:
    return data if isinstance(data, str) else str(data)


class StellarDS:
    """The synchronous StellarDS client.

    Args:
        access_token: a static access token (from the project's access tokens, or an OAuth access token).
        oauth: OAuth credentials; the client then refreshes the access token by itself, shortly before it expires
            and once after a 401.
        base_url: the API's address.
        project: the default project id for every call that takes ``project=``.
        on_tokens: called with the new :class:`~stellards.Tokens` whenever the client refreshes them: store them
            there. The SDK never writes tokens to disk.
        timeout: seconds (or an ``httpx.Timeout``) per request; ``None`` for no timeout.
        parse_decimals: parse JSON numbers with a fraction as ``decimal.Decimal`` instead of ``float`` (exact
            Decimal fields, but Real/Float fields become Decimal too).
        headers: extra headers for every request.
        http_client: an ``httpx.Client`` to use instead of the client's own (you then close it yourself).

    Use it as a context manager, or call :meth:`close`, to release its connections.
    """

    projects: sync.Projects
    tables: sync.Tables
    fields: sync.Fields
    records: sync.Records
    query: sync.Query
    procedures: sync.Procedures
    relations: sync.Relations
    roles: sync.Roles
    permissions: sync.Permissions
    audit: sync.Audit
    webhooks: sync.Webhooks
    users: sync.Users
    applications: sync.Applications
    project_tiers: sync.ProjectTiers
    oauth: sync.OAuth

    def __init__(
        self,
        access_token: str | None = None,
        *,
        oauth: OAuthCredentials | None = None,
        base_url: str = DEFAULT_BASE_URL,
        project: ProjectId | None = None,
        on_tokens: TokensCallback | None = None,
        timeout: TimeoutTypes = DEFAULT_TIMEOUT,
        parse_decimals: bool = False,
        headers: Mapping[str, str] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._core = SyncCore(
            access_token=access_token,
            oauth=oauth,
            base_url=base_url,
            timeout=timeout,
            on_tokens=on_tokens,
            project=project,
            parse_decimals=parse_decimals,
            headers=headers,
            http_client=http_client,
        )
        core = self._core
        self.projects = sync.Projects(core)
        self.tables = sync.Tables(core)
        self.fields = sync.Fields(core)
        self.records = sync.Records(core)
        self.query = sync.Query(core)
        self.procedures = sync.Procedures(core)
        self.relations = sync.Relations(core)
        self.roles = sync.Roles(core)
        self.permissions = sync.Permissions(core)
        self.audit = sync.Audit(core)
        self.webhooks = sync.Webhooks(core)
        self.users = sync.Users(core)
        self.applications = sync.Applications(core)
        self.project_tiers = sync.ProjectTiers(core)
        self.oauth = sync.OAuth(core)

    @property
    def access_token(self) -> str | None:
        """The access token in use (it changes when the client refreshes it)."""
        return self._core.tokens.access_token

    @property
    def project(self) -> str | None:
        """The default project."""
        return self._core.project

    def ping(self) -> str:
        """Checks that the API is reachable; returns ``"pong"``."""
        return self._core.request(ApiRequest("GET", "/v1/ping", parse=_ping_text, authenticated=False))

    def close(self) -> None:
        self._core.close()

    def __enter__(self) -> StellarDS:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"StellarDS(base_url={self._core.base_url!r}, project={self._core.project!r})"


class AsyncStellarDS:
    """The asynchronous StellarDS client: the same resources as :class:`StellarDS`, with ``await``.

    ``records.iter(...)`` is an async iterator (``async for``), and ``on_tokens`` may be a coroutine function.
    Use it as an async context manager, or ``await client.close()``.
    """

    projects: aio.Projects
    tables: aio.Tables
    fields: aio.Fields
    records: aio.Records
    query: aio.Query
    procedures: aio.Procedures
    relations: aio.Relations
    roles: aio.Roles
    permissions: aio.Permissions
    audit: aio.Audit
    webhooks: aio.Webhooks
    users: aio.Users
    applications: aio.Applications
    project_tiers: aio.ProjectTiers
    oauth: aio.OAuth

    def __init__(
        self,
        access_token: str | None = None,
        *,
        oauth: OAuthCredentials | None = None,
        base_url: str = DEFAULT_BASE_URL,
        project: ProjectId | None = None,
        on_tokens: TokensCallback | None = None,
        timeout: TimeoutTypes = DEFAULT_TIMEOUT,
        parse_decimals: bool = False,
        headers: Mapping[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._core = AsyncCore(
            access_token=access_token,
            oauth=oauth,
            base_url=base_url,
            timeout=timeout,
            on_tokens=on_tokens,
            project=project,
            parse_decimals=parse_decimals,
            headers=headers,
            http_client=http_client,
        )
        core = self._core
        self.projects = aio.Projects(core)
        self.tables = aio.Tables(core)
        self.fields = aio.Fields(core)
        self.records = aio.Records(core)
        self.query = aio.Query(core)
        self.procedures = aio.Procedures(core)
        self.relations = aio.Relations(core)
        self.roles = aio.Roles(core)
        self.permissions = aio.Permissions(core)
        self.audit = aio.Audit(core)
        self.webhooks = aio.Webhooks(core)
        self.users = aio.Users(core)
        self.applications = aio.Applications(core)
        self.project_tiers = aio.ProjectTiers(core)
        self.oauth = aio.OAuth(core)

    @property
    def access_token(self) -> str | None:
        return self._core.tokens.access_token

    @property
    def project(self) -> str | None:
        return self._core.project

    async def ping(self) -> str:
        """Checks that the API is reachable; returns ``"pong"``."""
        return await self._core.request(ApiRequest("GET", "/v1/ping", parse=_ping_text, authenticated=False))

    async def close(self) -> None:
        await self._core.close()

    async def __aenter__(self) -> AsyncStellarDS:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    def __repr__(self) -> str:
        return f"AsyncStellarDS(base_url={self._core.base_url!r}, project={self._core.project!r})"
