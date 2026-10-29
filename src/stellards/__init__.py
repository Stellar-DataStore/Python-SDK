"""The StellarDS SDK for Python.

>>> from stellards import StellarDS
>>> with StellarDS(access_token="...", project="your-project-id") as sds:
...     for table in sds.tables.list():
...         print(table.id, table.name)
"""

from __future__ import annotations

from . import oauth, webhooks
from ._client import AsyncStellarDS, StellarDS
from ._core import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, OAuthCredentials
from ._version import __version__
from .errors import (
    ApiConnectionError,
    ApiError,
    ApiTimeoutError,
    AuthenticationError,
    Message,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    StellarDSError,
    WebhookSignatureError,
)
from .field_types import FieldType
from .filters import Where, join, where
from .models import (
    AccessToken,
    Account,
    AuditEntry,
    AuditLog,
    CreatedAccessToken,
    DurationUnit,
    Field,
    Invitation,
    OAuthClient,
    OAuthDesign,
    Permission,
    Procedure,
    ProcedureParameter,
    ProcedureResult,
    ProcedureStep,
    ProcedureStepResult,
    Project,
    ProjectLogEntry,
    ProjectTier,
    QueryColumn,
    QueryResult,
    RecordPage,
    Relation,
    RelationCheck,
    Role,
    RoleMatrix,
    RoleMatrixRole,
    RoleMatrixRoleUpdate,
    RolePermissions,
    Table,
    TablePermissionDetails,
    TablePermissions,
    TablePosition,
    TableRole,
    TableRoles,
    Tokens,
    TopLevelRole,
    User,
    UserList,
    Webhook,
    WebhookDelivery,
    WebhookWithSecret,
)

__all__ = [
    "__version__",
    # clients
    "StellarDS",
    "AsyncStellarDS",
    "OAuthCredentials",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    # modules
    "oauth",
    "webhooks",
    # building requests
    "FieldType",
    "Where",
    "where",
    "join",
    "DurationUnit",
    "RolePermissions",
    "TablePermissions",
    "TablePosition",
    "ProcedureParameter",
    "ProcedureStep",
    "RoleMatrixRoleUpdate",
    "OAuthDesign",
    # errors
    "StellarDSError",
    "ApiError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "RateLimitError",
    "ApiConnectionError",
    "ApiTimeoutError",
    "WebhookSignatureError",
    "Message",
    # models
    "AccessToken",
    "Account",
    "AuditEntry",
    "AuditLog",
    "CreatedAccessToken",
    "Field",
    "Invitation",
    "OAuthClient",
    "Permission",
    "Procedure",
    "ProcedureResult",
    "ProcedureStepResult",
    "Project",
    "ProjectLogEntry",
    "ProjectTier",
    "QueryColumn",
    "QueryResult",
    "RecordPage",
    "Relation",
    "RelationCheck",
    "Role",
    "RoleMatrix",
    "RoleMatrixRole",
    "Table",
    "TablePermissionDetails",
    "TableRole",
    "TableRoles",
    "Tokens",
    "TopLevelRole",
    "User",
    "UserList",
    "Webhook",
    "WebhookDelivery",
    "WebhookWithSecret",
]
