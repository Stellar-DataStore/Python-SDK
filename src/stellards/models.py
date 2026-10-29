"""Typed objects for what StellarDS returns.

Every model is a dataclass built with ``Model.from_dict``, which is tolerant: unknown fields are ignored, missing
fields keep their default and a value of an unexpected type is kept as it came. The complete response object is
always available as ``model.raw``. Records are plain dicts, not models.
"""

from __future__ import annotations

import datetime as _dt
import enum
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, fields
from typing import Any, Callable, TypeVar

__all__ = [
    "Model",
    "Project",
    "Table",
    "Field",
    "RecordPage",
    "QueryColumn",
    "QueryResult",
    "ProcedureParameter",
    "ProcedureStep",
    "Procedure",
    "ProcedureStepResult",
    "ProcedureResult",
    "Relation",
    "RelationCheck",
    "TablePosition",
    "TablePermissions",
    "RolePermissions",
    "Role",
    "Permission",
    "TopLevelRole",
    "TablePermissionDetails",
    "TableRole",
    "TableRoles",
    "RoleMatrixTable",
    "RoleMatrixTablePermissions",
    "RoleMatrixRole",
    "RoleMatrix",
    "RoleMatrixRoleUpdate",
    "User",
    "UserList",
    "Invitation",
    "Account",
    "AuditEntry",
    "AuditLog",
    "ProjectLogEntry",
    "Webhook",
    "WebhookWithSecret",
    "WebhookDelivery",
    "AccessToken",
    "CreatedAccessToken",
    "OAuthClient",
    "ProjectTier",
    "OAuthDesign",
    "Tokens",
    "DurationUnit",
]

M = TypeVar("M", bound="Model")
T = TypeVar("T")


# --------------------------------------------------------------------------------------------------- converters


def parse_datetime(value: Any) -> Any:
    """Parses the ISO 8601 forms .NET writes (``Z``, up to 7 fractional digits). Leaves anything else alone."""
    if isinstance(value, _dt.datetime) or not isinstance(value, str):
        return value
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    match = re.match(r"^(.*T\d{2}:\d{2}:\d{2})\.(\d+)(.*)$", text)
    if match:
        text = f"{match.group(1)}.{match.group(2)[:6].ljust(6, '0')}{match.group(3)}"
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError:
        return value


def _int(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _float(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return value


def _list(item: Callable[[Any], Any] | None = None) -> Callable[[Any], Any]:
    def convert(value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [item(v) if item is not None and v is not None else v for v in value]

    return convert


def _model(cls: type[Model]) -> Callable[[Any], Any]:
    def convert(value: Any) -> Any:
        return cls.from_dict(value) if isinstance(value, Mapping) else value

    return convert


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _f(default: Any = None, *, parse: Callable[[Any], Any] | None = None, alias: str | None = None) -> Any:
    metadata = {"parse": parse, "alias": alias}
    if isinstance(default, (list, dict)):
        factory: Callable[[], Any] = type(default)
        return field(default_factory=factory, metadata=metadata)
    return field(default=default, metadata=metadata)


# --------------------------------------------------------------------------------------------------- base


class Model:
    """Base of every response model. ``raw`` holds the response object exactly as it came."""

    @classmethod
    def from_dict(cls: type[M], data: Any) -> M:
        source: Mapping[str, Any] = data if isinstance(data, Mapping) else {}
        lowered = {k.lower(): v for k, v in source.items() if isinstance(k, str)}
        kwargs: dict[str, Any] = {}
        for f in fields(cls):  # type: ignore[arg-type]
            alias = f.metadata.get("alias") or _camel(f.name)
            # Most responses are camelCase; the OAuth ones are snake_case.
            key = next((k for k in (alias.lower(), f.name.lower()) if k in lowered), None)
            if key is None:
                continue
            value = lowered[key]
            parse = f.metadata.get("parse")
            kwargs[f.name] = parse(value) if parse is not None and value is not None else value
        obj = cls(**kwargs)
        object.__setattr__(obj, "_raw", dict(source))
        return obj

    @property
    def raw(self) -> dict[str, Any]:
        """The response object this model was parsed from."""
        return dict(self.__dict__.get("_raw", {}))


# --------------------------------------------------------------------------------------------------- schema


@dataclass
class Project(Model):
    id: str = ""
    name: str = ""
    description: str = ""
    is_multitenant: bool = False
    allow_new_users: bool = False
    tier_id: int | None = _f(None, parse=_int)


@dataclass
class Table(Model):
    id: int = _f(0, parse=_int)
    name: str = ""
    description: str | None = None
    is_multitenant: bool = False


@dataclass
class Field(Model):
    id: int = _f(0, parse=_int)
    name: str = ""
    type: str = ""
    #: An Enum field's allowed values.
    options: list[str] = _f([])


# --------------------------------------------------------------------------------------------------- data


@dataclass
class RecordPage:
    """One page of records, plus the total number of records matching the query."""

    records: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.records[index]


@dataclass
class QueryColumn(Model):
    name: str | None = None
    type: str | None = None


@dataclass
class QueryResult(Model):
    """The result of a custom query or of one procedure step."""

    columns: list[QueryColumn] = _f([], parse=_list(_model(QueryColumn)))
    rows: list[Any] = _f([])
    count: int = _f(0, parse=_int)
    #: True when the server cut the result off at its row limit.
    truncated: bool = False
    duration_ms: int = _f(0, parse=_int)


# --------------------------------------------------------------------------------------------------- procedures


@dataclass
class ProcedureParameter(Model):
    name: str = ""
    #: A field type such as ``"Int"`` or ``"NVarChar(100)"``.
    type: str = ""
    required: bool = False
    default_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type, "required": self.required, "defaultValue": self.default_value}


@dataclass
class ProcedureStep(Model):
    name: str = ""
    sql: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "sql": self.sql}


@dataclass
class Procedure(Model):
    name: str = ""
    description: str | None = None
    version: int = _f(0, parse=_int)
    created_at: _dt.datetime | None = _f(None, parse=parse_datetime)
    updated_at: _dt.datetime | None = _f(None, parse=parse_datetime)
    parameters: list[ProcedureParameter] = _f([], parse=_list(_model(ProcedureParameter)))
    steps: list[ProcedureStep] = _f([], parse=_list(_model(ProcedureStep)))
    #: What is wrong with the procedure (e.g. a table it uses was deleted); empty when it can run.
    problems: list[str] = _f([])


@dataclass
class ProcedureStepResult(QueryResult):
    step: str | None = None


@dataclass
class ProcedureResult(Model):
    name: str | None = None
    version: int = _f(0, parse=_int)
    results: list[ProcedureStepResult] = _f([], parse=_list(_model(ProcedureStepResult)))
    duration_ms: int = _f(0, parse=_int)


# --------------------------------------------------------------------------------------------------- relations


@dataclass
class Relation(Model):
    id: int = _f(0, parse=_int)
    name: str = ""
    from_table_id: int = _f(0, parse=_int)
    from_table_name: str = ""
    from_field_id: int = _f(0, parse=_int)
    from_field_name: str = ""
    to_table_id: int = _f(0, parse=_int)
    to_table_name: str = ""
    #: ``"Restrict"``, ``"Cascade"`` or ``"SetNull"``.
    on_delete: str = ""
    display_field_id: int | None = _f(None, parse=_int)
    display_field_name: str | None = None


@dataclass
class RelationCheck(Model):
    field_type: str | None = None
    requires_conversion: bool = False
    is_valid: bool = False
    problem: str | None = None
    orphan_count: int = _f(0, parse=_int)


@dataclass
class TablePosition(Model):
    """Where a table sits on the database designer's canvas."""

    table_id: int = _f(0, parse=_int)
    x: float = _f(0.0, parse=_float)
    y: float = _f(0.0, parse=_float)

    def to_dict(self) -> dict[str, Any]:
        return {"tableId": self.table_id, "x": self.x, "y": self.y}


# --------------------------------------------------------------------------------------------------- roles


@dataclass
class TablePermissions(Model):
    """What a role may do with one table (or, without ``table_name``, with tables by default)."""

    table_name: str | None = None
    read_table: bool = False
    update_table_metadata: bool = False
    update_table: bool = False
    create_record: bool = False
    read_records: bool = False
    delete_record: bool = False
    update_record: bool = False

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {} if self.table_name is None else {"tableName": self.table_name}
        result.update(
            readTable=self.read_table,
            updateTableMetadata=self.update_table_metadata,
            updateTable=self.update_table,
            createRecord=self.create_record,
            readRecords=self.read_records,
            deleteRecord=self.delete_record,
            updateRecord=self.update_record,
        )
        return result


@dataclass
class RolePermissions(Model):
    """A role's project-level permissions, its per-table permissions and its default table permission."""

    update_project: bool = False
    delete_project: bool = False
    create_tables: bool = False
    delete_tables: bool = False
    ignore_multitenant: bool = False
    manage_access_tokens: bool = False
    manage_clients: bool = False
    manage_webhooks: bool = False
    update_permissions: bool = False
    invite_users: bool = False
    read_members: bool = False
    remove_members: bool = False
    tables: list[TablePermissions] = _f([], parse=_list(_model(TablePermissions)))
    default_table_permission: TablePermissions | None = _f(None, parse=_model(TablePermissions))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            _camel(name): getattr(self, name)
            for name in (
                "update_project",
                "delete_project",
                "create_tables",
                "delete_tables",
                "ignore_multitenant",
                "manage_access_tokens",
                "manage_clients",
                "manage_webhooks",
                "update_permissions",
                "invite_users",
                "read_members",
                "remove_members",
            )
        }
        result["tables"] = [t.to_dict() for t in self.tables]
        if self.default_table_permission is not None:
            result["defaultTablePermission"] = self.default_table_permission.to_dict()
        return result


@dataclass
class Role(Model):
    id: str = ""
    name: str = ""
    description: str = ""
    project_id: str = ""
    #: Absent in the "simple" role list.
    permissions: RolePermissions | None = _f(None, parse=_model(RolePermissions))


@dataclass
class Permission(Model):
    name: str = ""
    description: str = ""
    #: Whether the role has it; ``None`` in the plain permission list.
    enabled: bool | None = None


@dataclass
class TopLevelRole(Model):
    permissions: list[Permission] = _f([], parse=_list(_model(Permission)))
    default_table_permissions: list[Permission] = _f([], parse=_list(_model(Permission)))
    tables: list[str] = _f([])


@dataclass
class TablePermissionDetails(Model):
    """One role's permissions on one table, each with a description."""

    table_name: str = ""
    permissions: list[Permission] = _f([], parse=_list(_model(Permission)))


@dataclass
class TableRole(Model):
    id: str = ""
    name: str = ""
    permissions: list[Permission] = _f([], parse=_list(_model(Permission)))


@dataclass
class TableRoles(Model):
    """Every role's permissions on one table."""

    table_name: str = ""
    roles: list[TableRole] = _f([], parse=_list(_model(TableRole)))


@dataclass
class RoleMatrixTable(Model):
    id: int = _f(0, parse=_int)
    name: str = ""


@dataclass
class RoleMatrixTablePermissions(Model):
    table_id: int = _f(0, parse=_int)
    permissions: list[int] = _f([])


@dataclass
class RoleMatrixRole(Model):
    id: str = ""
    name: str = ""
    description: str | None = None
    #: Permission ids, as listed by ``permissions.info()``.
    permissions: list[int] = _f([])
    default_table_permissions: list[int] = _f([])
    tables: list[RoleMatrixTablePermissions] = _f([], parse=_list(_model(RoleMatrixTablePermissions)))
    members: list[str] = _f([])
    member_count: int = _f(0, parse=_int)
    access_tokens: list[str] = _f([])
    clients: list[str] = _f([])


@dataclass
class RoleMatrix(Model):
    """Every role of a project with its permissions on every table, as one grid."""

    tables: list[RoleMatrixTable] = _f([], parse=_list(_model(RoleMatrixTable)))
    roles: list[RoleMatrixRole] = _f([], parse=_list(_model(RoleMatrixRole)))


@dataclass
class RoleMatrixRoleUpdate:
    """One role's row in ``roles.update_matrix(...)``. Leave a part ``None`` to keep it as it is."""

    role_id: str
    name: str | None = None
    description: str | None = None
    permissions: list[int] | None = None
    default_table_permissions: list[int] | None = None
    #: Permission ids per table id.
    tables: Mapping[int, list[int]] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"roleId": str(self.role_id)}
        if self.name is not None:
            result["name"] = self.name
        if self.description is not None:
            result["description"] = self.description
        if self.permissions is not None:
            result["permissions"] = list(self.permissions)
        if self.default_table_permissions is not None:
            result["defaultTablePermissions"] = list(self.default_table_permissions)
        if self.tables is not None:
            result["tables"] = [
                {"tableId": table_id, "permissions": list(perms)} for table_id, perms in self.tables.items()
            ]
        return result


# --------------------------------------------------------------------------------------------------- users


@dataclass
class User(Model):
    username: str | None = None
    email: str = ""
    role: str | None = None
    is_owner: bool = False
    has_application_access: bool = False


@dataclass
class UserList(Model):
    total_count: int = _f(0, parse=_int)
    users: list[User] = _f([], parse=_list(_model(User)))


@dataclass
class Invitation(Model):
    id: int = _f(0, parse=_int)
    email: str = ""
    inviter_id: str = ""
    role_id: str = ""
    role_name: str = ""
    application_access: bool = False
    existing_user: bool = False


@dataclass
class Account(Model):
    """The signed-in user."""

    username: str = ""
    email: str = ""


# --------------------------------------------------------------------------------------------------- audit


@dataclass
class AuditEntry(Model):
    id: str = ""
    table_name: str = ""
    date_time: _dt.datetime | None = _f(None, parse=parse_datetime)
    user: User | None = _f(None, parse=_model(User))
    operation: str = ""
    difference: str = ""
    state: str = ""
    state_by_user: User | None = _f(None, parse=_model(User))


@dataclass
class AuditLog(Model):
    audits: list[AuditEntry] = _f([], parse=_list(_model(AuditEntry)))
    count: int = _f(0, parse=_int)


@dataclass
class ProjectLogEntry(Model):
    """One API request made to a project."""

    user_id: str | None = None
    client_id: str | None = None
    project_id: str | None = None
    remote_ip: str = ""
    access_token_id: str | None = None
    request_date_time: _dt.datetime | None = _f(None, parse=parse_datetime)
    request_method: str = ""
    request_path_and_query: str = ""
    response_status_code: int = _f(0, parse=_int)


# --------------------------------------------------------------------------------------------------- webhooks


@dataclass
class Webhook(Model):
    id: int = _f(0, parse=_int)
    url: str = ""
    #: Event types such as ``"record.created"``; the server fills in its default when you send none.
    events: list[str] = _f([])
    #: Only these tables; empty means every table.
    table_ids: list[int] = _f([], parse=_list(_int))
    is_active: bool = False
    disabled_at: _dt.datetime | None = _f(None, parse=parse_datetime)
    failing_since: _dt.datetime | None = _f(None, parse=parse_datetime)
    previous_secret_expires_at: _dt.datetime | None = _f(None, parse=parse_datetime)
    created_at: _dt.datetime | None = _f(None, parse=parse_datetime)
    updated_at: _dt.datetime | None = _f(None, parse=parse_datetime)


@dataclass
class WebhookWithSecret(Webhook):
    """A webhook together with its signing secret, which is only ever shown when it is created or rotated."""

    secret: str = ""


@dataclass
class WebhookDelivery(Model):
    id: int = _f(0, parse=_int)
    event_id: str | None = None
    event_type: str | None = None
    status: str | None = None
    attempts: int = _f(0, parse=_int)
    created_at: _dt.datetime | None = _f(None, parse=parse_datetime)
    next_attempt_at: _dt.datetime | None = _f(None, parse=parse_datetime)
    delivered_at: _dt.datetime | None = _f(None, parse=parse_datetime)
    last_status_code: int | None = _f(None, parse=_int)
    last_response: str | None = None
    payload: str | None = None


# --------------------------------------------------------------------------------------------------- applications


class DurationUnit(enum.IntEnum):
    """The unit of an access token's lifetime (``span``)."""

    MINUTES = 0
    HOURS = 1
    DAYS = 2
    WEEKS = 3
    MONTHS = 4
    YEARS = 5
    #: The token never expires (``duration`` is ignored).
    UNLIMITED = -1


@dataclass
class AccessToken(Model):
    id: str = ""
    name: str = ""
    domain: str | None = None
    duration: int = _f(0, parse=_int)
    #: The unit of ``duration`` (see :class:`stellards.DurationUnit`).
    span: int = _f(0, parse=_int)
    end_time: _dt.datetime | None = _f(None, parse=parse_datetime)
    role: Role | None = _f(None, parse=_model(Role))
    created_at: _dt.datetime | None = _f(None, parse=parse_datetime)


@dataclass
class CreatedAccessToken(Model):
    """A new access token. ``access_token`` is only shown now: store it."""

    access_token: str = ""
    refresh_token: str | None = None
    expires_in: int = _f(0, parse=_int)
    token_type: str = "Bearer"
    metadata: AccessToken | None = _f(None, parse=_model(AccessToken))


@dataclass
class OAuthClient(Model):
    name: str = ""
    client_id: str = ""
    #: Only filled in when the client is created or its secret regenerated.
    client_secret: str | None = None
    redirect_urls: list[str] = _f([])
    domain: str | None = None
    role: Role | None = _f(None, parse=_model(Role))


@dataclass
class ProjectTier(Model):
    name: str = ""
    users: int = _f(0, parse=_int)
    tables: int = _f(0, parse=_int)
    max_requests: int = _f(0, parse=_int)


@dataclass
class OAuthDesign(Model):
    """How the sign-in page of a project's OAuth clients looks."""

    id: str | None = None
    project_id: str | None = None
    use_custom_design: bool = False
    primary_color: str | None = None
    secondary_color: str | None = None
    font_color: str | None = None
    button_color: str | None = None
    degrees: int = _f(0, parse=_int)
    base64_image: str | None = None
    use_solid_background: bool = False
    title: str | None = None
    subtitle: str | None = None
    button_radius: int | None = _f(None, parse=_int)
    hide_sign_up_link: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "useCustomDesign": self.use_custom_design,
            "primaryColor": self.primary_color,
            "secondaryColor": self.secondary_color,
            "fontColor": self.font_color,
            "buttonColor": self.button_color,
            "degrees": self.degrees,
            "base64Image": self.base64_image,
            "projectId": self.project_id,
            "useSolidBackground": self.use_solid_background,
            "title": self.title,
            "subtitle": self.subtitle,
            "buttonRadius": self.button_radius,
            "hideSignUpLink": self.hide_sign_up_link,
        }


# --------------------------------------------------------------------------------------------------- oauth


@dataclass
class Tokens(Model):
    """An OAuth token set, as the token endpoint returns it.

    ``expires_at`` is computed from ``expires_in`` when the tokens are received (UTC).
    """

    access_token: str = ""
    refresh_token: str | None = None
    expires_in: int = _f(0, parse=_int)
    token_type: str = "Bearer"
    expires_at: _dt.datetime | None = None

    @classmethod
    def from_response(cls, data: Any, *, now: _dt.datetime | None = None) -> Tokens:
        tokens = cls.from_dict(data)
        if tokens.expires_at is None and isinstance(tokens.expires_in, int) and tokens.expires_in > 0:
            moment = now or _dt.datetime.now(_dt.timezone.utc)
            tokens.expires_at = moment + _dt.timedelta(seconds=tokens.expires_in)
        return tokens
