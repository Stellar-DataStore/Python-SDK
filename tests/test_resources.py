"""Every resource method: HTTP method, path, query parameters, body and result type, for both clients."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
import respx

from stellards import (
    AccessToken,
    Account,
    AsyncStellarDS,
    AuditLog,
    CreatedAccessToken,
    DurationUnit,
    Field,
    FieldType,
    Invitation,
    OAuthClient,
    OAuthDesign,
    Permission,
    Procedure,
    ProcedureResult,
    Project,
    ProjectLogEntry,
    ProjectTier,
    Relation,
    RelationCheck,
    Role,
    RoleMatrix,
    RoleMatrixRoleUpdate,
    RolePermissions,
    StellarDS,
    Table,
    TablePermissionDetails,
    TablePermissions,
    TablePosition,
    TableRoles,
    Tokens,
    TopLevelRole,
    UserList,
    Webhook,
    WebhookDelivery,
    WebhookWithSecret,
)

from .conftest import PROJECT, ok

ROLE = "11111111-2222-3333-4444-555555555555"
P = {"project": PROJECT}


@dataclass
class Case:
    call: str
    args: tuple[Any, ...]
    method: str
    path: str
    params: dict[str, str]
    data: Any = None
    body: Any = None
    result: Any = None
    kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.call


CASES = [
    # projects
    Case("projects.list", (), "GET", "/v1/schema/project", {}, [{"id": PROJECT, "name": "P"}], result=list),
    Case("projects.get", (), "GET", "/v1/schema/project", P, {"id": PROJECT, "tierId": 2}, result=Project),
    Case(
        "projects.create",
        ("New",),
        "POST",
        "/v1/schema/project",
        {},
        {"id": PROJECT, "name": "New"},
        body={"name": "New", "description": None, "isMultitenant": False, "allowNewUsers": False},
        result=Project,
    ),
    Case(
        "projects.update",
        (),
        "PUT",
        "/v1/schema/project",
        P,
        {"id": PROJECT, "name": "Renamed"},
        body={"name": "Renamed", "description": "d", "isMultitenant": True, "allowNewUsers": False},
        result=Project,
        kwargs={"name": "Renamed", "description": "d", "is_multitenant": True, "allow_new_users": False},
    ),
    Case("projects.delete", (), "DELETE", "/v1/schema/project", P),
    Case(
        "projects.users",
        (),
        "GET",
        "/v1/schema/project/users",
        {**P, "page": "2", "pageSize": "10"},
        {"totalCount": 1, "users": [{"email": "a@b.c", "isOwner": True}]},
        result=UserList,
        kwargs={"page": 2, "page_size": 10},
    ),
    Case("projects.user_count", (), "GET", "/v1/schema/project/user-count", P, 5, result=int),
    Case("projects.invited_users", (), "GET", "/v1/schema/project/invited-users", P, [{"id": 1}], result=list),
    Case("projects.app_access", (), "GET", "/v1/schema/project/app-access", {}, [], result=list),
    Case(
        "projects.log",
        ("2024-05-01",),
        "GET",
        "/v1/schema/project/project-log",
        {"id": PROJECT, "logDate": "2024-05-01"},
        [{"requestMethod": "GET", "responseStatusCode": 200}],
        result=list,
    ),
    Case(
        "projects.get_oauth_design",
        (),
        "GET",
        "/v1/schema/project/oauth-design",
        {"projectid": PROJECT},
        {"useCustomDesign": True},
        result=OAuthDesign,
    ),
    Case(
        "projects.update_oauth_design",
        (OAuthDesign(title="Hi"),),
        "POST",
        "/v1/schema/project/oauth-design",
        {"id": "d1", **P},
        {"title": "Hi"},
        result=OAuthDesign,
        kwargs={"design_id": "d1"},
    ),
    # tables
    Case("tables.list", (), "GET", "/v1/schema/table", P, [{"id": 1}], result=list),
    Case("tables.get", (5,), "GET", "/v1/schema/table", {**P, "table": "5"}, {"id": 5}, result=Table),
    Case(
        "tables.create",
        ("Orders",),
        "POST",
        "/v1/schema/table",
        P,
        {"id": 5, "name": "Orders"},
        body={"name": "Orders", "description": "x", "isMultitenant": True},
        result=Table,
        kwargs={"description": "x", "is_multitenant": True},
    ),
    Case(
        "tables.update",
        (5,),
        "PUT",
        "/v1/schema/table",
        {**P, "table": "5"},
        [{"id": 4, "name": "Other"}, {"id": 5, "name": "Renamed"}],
        body={"name": "Renamed", "description": "", "isMultitenant": False},
        result=Table,
        kwargs={"name": "Renamed", "description": "", "is_multitenant": False},
    ),
    Case("tables.delete", (5,), "DELETE", "/v1/schema/table", {**P, "table": "5"}),
    # fields
    Case("fields.list", (5,), "GET", "/v1/schema/table/field", {**P, "table": "5"}, [{"id": 1}], result=list),
    Case(
        "fields.get",
        (5, 9),
        "GET",
        "/v1/schema/table/field",
        {**P, "table": "5", "field": "9"},
        {"id": 9},
        result=Field,
    ),
    Case(
        "fields.create",
        (5, "status", FieldType.enum(["new", "done"])),
        "POST",
        "/v1/schema/table/field",
        {**P, "table": "5"},
        {"id": 9, "name": "status", "type": "Enum", "options": ["new", "done"]},
        body={"name": "status", "type": "Enum", "options": ["new", "done"]},
        result=Field,
    ),
    Case(
        "fields.update",
        (5, 9),
        "PUT",
        "/v1/schema/table/field",
        {**P, "table": "5", "field": "9"},
        {"id": 9},
        body={"name": "status", "type": "Enum", "options": ["open", "done"], "replaceOptions": {"new": "open"}},
        result=Field,
        kwargs={
            "name": "status",
            "type": "Enum",
            "options": ["open", "done"],
            "replace_options": {"new": "open"},
        },
    ),
    Case("fields.delete", (5, 9), "DELETE", "/v1/schema/table/field", {**P, "table": "5", "field": "9"}),
    # procedures
    Case("procedures.list", (), "GET", "/v1/procedures", P, [{"name": "a"}], result=list),
    Case("procedures.get", ("monthly/report",), "GET", "/v1/procedures/monthly/report", P, {}, result=Procedure),
    Case(
        "procedures.create",
        ("report",),
        "POST",
        "/v1/procedures",
        P,
        {"name": "report", "version": 1},
        body={
            "name": "report",
            "description": None,
            "parameters": [{"name": "year", "type": "Int", "required": True, "defaultValue": None}],
            "steps": [{"name": "s1", "sql": "select 1"}],
        },
        result=Procedure,
        kwargs={
            "steps": [("s1", "select 1")],
            "parameters": [{"name": "year", "type": "Int", "required": True, "defaultValue": None}],
        },
    ),
    Case(
        "procedures.update",
        ("report",),
        "PUT",
        "/v1/procedures/report",
        P,
        {"name": "report", "version": 2},
        body={
            "name": "report2",
            "description": "d",
            "parameters": [],
            "steps": [{"name": "s", "sql": "x"}],
            "version": 1,
        },
        result=Procedure,
        kwargs={
            "new_name": "report2",
            "description": "d",
            "parameters": [],
            "steps": [{"name": "s", "sql": "x"}],
            "version": 1,
        },
    ),
    Case("procedures.delete", ("report",), "DELETE", "/v1/procedures/report", P),
    Case(
        "procedures.execute",
        ("report", {"year": 2024}),
        "POST",
        "/v1/procedures/report/execute",
        P,
        {"name": "report", "results": [{"step": "s1", "rows": [{"n": 1}], "count": 1}]},
        body={"parameters": {"year": 2024}},
        result=ProcedureResult,
    ),
    # relations
    Case("relations.list", (), "GET", "/v1/schema/relation", P, [{"id": 1}], result=list, kwargs={}),
    Case(
        "relations.check",
        (5, 9, 6),
        "GET",
        "/v1/schema/relation/check",
        {**P, "table": "5", "field": "9", "toTable": "6"},
        {"isValid": True, "orphanCount": 0},
        result=RelationCheck,
    ),
    Case(
        "relations.create",
        (5,),
        "POST",
        "/v1/schema/relation",
        {**P, "table": "5"},
        {"id": 3},
        body={
            "name": None,
            "fromFieldId": 9,
            "newFieldName": None,
            "toTableId": 6,
            "onDelete": "Cascade",
            "displayFieldId": None,
            "convertToBigInt": False,
            "orphanHandling": "Abort",
        },
        result=Relation,
        kwargs={"to_table": 6, "from_field": 9, "on_delete": "Cascade"},
    ),
    Case(
        "relations.update",
        (5, 3),
        "PUT",
        "/v1/schema/relation",
        {**P, "table": "5", "relation": "3"},
        {"id": 3},
        body={"name": None, "onDelete": "SetNull", "displayFieldId": None},
        result=Relation,
        kwargs={"on_delete": "SetNull"},
    ),
    Case("relations.delete", (5, 3), "DELETE", "/v1/schema/relation", {**P, "table": "5", "relation": "3"}),
    Case(
        "relations.get_layout",
        (),
        "GET",
        "/v1/schema/relation/layout",
        P,
        [{"tableId": 5, "x": 1, "y": 2.5}],
        result=list,
    ),
    Case(
        "relations.save_layout",
        ([TablePosition(table_id=5, x=10, y=20)],),
        "PUT",
        "/v1/schema/relation/layout",
        P,
        [{"tableId": 5, "x": 10, "y": 20}],
        body=[{"tableId": 5, "x": 10, "y": 20}],
        result=list,
    ),
    # roles
    Case("roles.list", (), "GET", "/v1/role", P, [{"id": ROLE}], result=list),
    Case(
        "roles.get",
        (ROLE,),
        "GET",
        "/v1/role",
        {**P, "role": ROLE},
        {"id": ROLE, "permissions": {"updateProject": True}},
        result=Role,
    ),
    Case("roles.simple", (), "GET", "/v1/role/simple", P, [{"id": ROLE}], result=list),
    Case(
        "roles.top_level",
        (ROLE,),
        "GET",
        "/v1/role/top-level",
        {**P, "role": ROLE},
        {"tables": ["A"]},
        result=TopLevelRole,
    ),
    Case(
        "roles.table_permissions",
        (ROLE, "Orders"),
        "GET",
        "/v1/role/table",
        {**P, "role": ROLE, "table": "Orders"},
        {"tableName": "Orders"},
        result=TablePermissionDetails,
    ),
    Case(
        "roles.table_roles",
        ("Orders",),
        "GET",
        "/v1/role/table-role-permissions",
        {**P, "tableName": "Orders"},
        {"tableName": "Orders", "roles": []},
        result=TableRoles,
    ),
    Case("roles.template", (), "GET", "/v1/role/template", P, {"name": ""}, result=Role),
    Case(
        "roles.create",
        ("Editors", RolePermissions(create_tables=True)),
        "POST",
        "/v1/role",
        P,
        {"id": ROLE},
        result=Role,
    ),
    Case(
        "roles.update",
        (ROLE,),
        "PUT",
        "/v1/role",
        {**P, "role": ROLE},
        {"id": ROLE},
        result=Role,
        kwargs={"name": "Editors", "permissions": {"createTables": True}, "description": "d"},
        body={"name": "Editors", "description": "d", "permissions": {"createTables": True}},
    ),
    Case("roles.delete", (ROLE,), "DELETE", "/v1/role", {**P, "role": ROLE}),
    Case(
        "roles.duplicate",
        (ROLE,),
        "POST",
        "/v1/role/duplicate",
        {**P, "roleId": ROLE},
        {"id": "x"},
        body={"name": "Copy", "description": ""},
        result=Role,
        kwargs={"name": "Copy"},
    ),
    Case(
        "roles.update_table",
        (ROLE, TablePermissions(table_name="Orders", read_records=True)),
        "PUT",
        "/v1/role/table",
        {**P, "role": ROLE},
        {"id": ROLE},
        result=Role,
    ),
    Case(
        "roles.matrix",
        (),
        "GET",
        "/v1/role/matrix",
        P,
        {"tables": [{"id": 1, "name": "A"}], "roles": []},
        result=RoleMatrix,
    ),
    Case(
        "roles.update_matrix",
        ([RoleMatrixRoleUpdate(role_id=ROLE, permissions=[1, 2], tables={5: [10, 14]})],),
        "PUT",
        "/v1/role/matrix",
        P,
        {"tables": [], "roles": []},
        body={"roles": [{"roleId": ROLE, "permissions": [1, 2], "tables": [{"tableId": 5, "permissions": [10, 14]}]}]},
        result=RoleMatrix,
    ),
    Case(
        "permissions.info",
        (),
        "GET",
        "/v1/permission/info",
        {},
        [{"name": "ReadTable", "description": "d"}],
        result=list,
    ),
    # audit
    Case(
        "audit.schema",
        (),
        "GET",
        "/v1/logging/schema",
        {**P, "take": "10", "offset": "0"},
        {"audits": [{"id": "a", "dateTime": "2024-01-02T03:04:05.1234567Z"}], "count": 1},
        result=AuditLog,
    ),
    Case(
        "audit.management",
        (),
        "GET",
        "/v1/logging/management",
        {**P, "take": "5", "offset": "5"},
        {},
        result=AuditLog,
        kwargs={"take": 5, "offset": 5},
    ),
    Case(
        "audit.rollback",
        ("tx-1",),
        "PUT",
        "/v1/logging/rollback",
        {**P, "transactionId": "tx-1", "force": "true"},
        None,
        kwargs={"force": True},
    ),
    # webhooks
    Case("webhooks.list", (), "GET", "/v1/webhooks", P, [{"id": 1}], result=list),
    Case("webhooks.get", (1,), "GET", "/v1/webhooks/1", P, {"id": 1}, result=Webhook),
    Case(
        "webhooks.create",
        ("https://example.com/hook",),
        "POST",
        "/v1/webhooks",
        P,
        {"id": 1, "secret": "whsec_abc"},
        body={"url": "https://example.com/hook", "events": ["record.created"], "tableIds": [5], "isActive": True},
        result=WebhookWithSecret,
        kwargs={"events": ["record.created"], "table_ids": [5]},
    ),
    Case(
        "webhooks.update",
        (1,),
        "PUT",
        "/v1/webhooks/1",
        P,
        {"id": 1},
        body={"url": "https://x", "events": [], "tableIds": [], "isActive": False},
        result=Webhook,
        kwargs={"url": "https://x", "events": [], "table_ids": [], "is_active": False},
    ),
    Case("webhooks.delete", (1,), "DELETE", "/v1/webhooks/1", P),
    Case(
        "webhooks.test", (1,), "POST", "/v1/webhooks/1/test", P, {"id": 7, "eventType": "ping"}, result=WebhookDelivery
    ),
    Case(
        "webhooks.rotate_secret",
        (1,),
        "POST",
        "/v1/webhooks/1/rotate-secret",
        P,
        {"id": 1, "secret": "whsec_new"},
        result=WebhookWithSecret,
    ),
    Case(
        "webhooks.deliveries",
        (1,),
        "GET",
        "/v1/webhooks/1/deliveries",
        {**P, "take": "20"},
        [{"id": 7}],
        result=list,
        kwargs={"take": 20},
    ),
    Case(
        "webhooks.redeliver",
        (1, 7),
        "POST",
        "/v1/webhooks/1/deliveries/7/redeliver",
        P,
        {"id": 8},
        result=WebhookDelivery,
    ),
    # users
    Case("users.me", (), "GET", "/v1/user", {}, {"username": "u", "email": "u@x"}, result=Account),
    Case("users.delete_me", (), "DELETE", "/v1/user", {}),
    Case(
        "users.permissions",
        (),
        "GET",
        "/v1/user/permissions",
        {"projectId": PROJECT},
        {"readMembers": True},
        result=RolePermissions,
    ),
    Case(
        "users.invite",
        ("a@b.c", ROLE),
        "POST",
        "/v1/user/invite",
        P,
        None,
        body={"email": "a@b.c", "role": ROLE, "allowAppAccess": True},
        kwargs={"allow_app_access": True},
    ),
    Case(
        "users.update_invitation",
        (3,),
        "PUT",
        "/v1/user/invitation",
        {**P, "id": "3"},
        None,
        body={"email": "a@b.c", "role": ROLE, "allowAppAccess": False},
        kwargs={"email": "a@b.c", "role": ROLE},
    ),
    Case("users.revoke_invitation", (3,), "DELETE", "/v1/user/revoke-invitation", {**P, "id": "3"}),
    Case(
        "users.update_access",
        ("a@b.c",),
        "PUT",
        "/v1/user/user-access",
        P,
        None,
        body={"email": "a@b.c", "role": ROLE, "hasApplicationAccess": True},
        kwargs={"role": ROLE, "has_application_access": True},
    ),
    Case("users.remove_access", ("a@b.c",), "DELETE", "/v1/user/remove-user-access", {**P, "email": "a@b.c"}),
    # applications
    Case("applications.access_tokens", (), "GET", "/v1/application/access-token", P, [{"id": "t"}], result=list),
    Case(
        "applications.create_access_token",
        ("CI",),
        "POST",
        "/v1/application/access-token",
        P,
        {"access_token": "jwt", "expires_in": 60, "metadata": {"id": "t", "name": "CI"}},
        body={"name": "CI", "role": ROLE, "domain": None, "duration": 3, "span": 2},
        result=CreatedAccessToken,
        kwargs={"role": ROLE, "duration": 3, "span": DurationUnit.DAYS},
    ),
    Case(
        "applications.update_access_token",
        ("t",),
        "PUT",
        "/v1/application/access-token",
        P,
        {"accessToken": {"id": "t"}},
        body={"accessTokenId": "t", "name": "CI", "role": ROLE, "domain": None, "duration": 1, "span": -1},
        kwargs={"name": "CI", "role": ROLE, "duration": 1, "span": DurationUnit.UNLIMITED},
    ),
    Case(
        "applications.delete_access_token",
        ("t",),
        "DELETE",
        "/v1/application/access-token",
        {**P, "accessTokenId": "t"},
    ),
    Case(
        "applications.regenerate_access_token",
        ("t",),
        "POST",
        "/v1/application/generate-jwt-token",
        P,
        {"access_token": "new", "expires_in": 10},
        body="t",
        result=Tokens,
    ),
    Case("applications.clients", (), "GET", "/v1/application/client", P, [{"clientId": "c"}], result=list),
    Case(
        "applications.create_client",
        ("App",),
        "POST",
        "/v1/application/client",
        P,
        {"clientId": "c", "clientSecret": "s"},
        body={"name": "App", "role": ROLE, "redirectUrls": ["https://a/cb"]},
        result=OAuthClient,
        kwargs={"role": ROLE, "redirect_urls": ["https://a/cb"]},
    ),
    Case(
        "applications.update_client",
        ("c",),
        "PUT",
        "/v1/application/client",
        P,
        {"clientId": "c"},
        body={"clientId": "c", "name": "App", "role": ROLE, "redirectUrls": []},
        result=OAuthClient,
        kwargs={"name": "App", "role": ROLE, "redirect_urls": []},
    ),
    Case("applications.delete_client", ("c",), "DELETE", "/v1/application/client", {**P, "clientId": "c"}),
    Case(
        "applications.regenerate_client_secret",
        ("c",),
        "POST",
        "/v1/application/generate-new-secret",
        P,
        {"clientId": "c", "clientSecret": "s2"},
        body="c",
        result=OAuthClient,
    ),
    # tiers
    Case(
        "project_tiers.get", (), "GET", "/v1/project-tier", P, {"name": "Free", "maxRequests": 1000}, result=ProjectTier
    ),
    Case("project_tiers.current", (), "GET", "/v1/project-tier/current", P, {"name": "Free"}, result=ProjectTier),
]

_RESULT_ITEM_TYPES = {
    "projects.list": Project,
    "projects.app_access": Project,
    "projects.invited_users": Invitation,
    "projects.log": ProjectLogEntry,
    "tables.list": Table,
    "fields.list": Field,
    "procedures.list": Procedure,
    "relations.list": Relation,
    "relations.get_layout": TablePosition,
    "relations.save_layout": TablePosition,
    "roles.list": Role,
    "roles.simple": Role,
    "permissions.info": Permission,
    "webhooks.list": Webhook,
    "webhooks.deliveries": WebhookDelivery,
    "applications.access_tokens": AccessToken,
    "applications.clients": OAuthClient,
}


def _check(case: Case, route: respx.Route, result: Any) -> None:
    request = route.calls.last.request
    assert request.method == case.method
    assert dict(request.url.params) == case.params
    if case.body is not None:
        assert json.loads(request.content) == case.body
    if case.result is None:
        assert result is None or case.data is None or result == case.data
    elif case.result is list:
        assert isinstance(result, list)
        item_type = _RESULT_ITEM_TYPES[case.call]
        assert all(isinstance(item, item_type) for item in result)
    else:
        assert isinstance(result, case.result)


def _resolve(client: Any, call: str) -> Any:
    resource, method = call.split(".")
    return getattr(getattr(client, resource), method)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_sync(case: Case, sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.route(method=case.method, path=case.path).mock(return_value=ok(case.data))
    result = _resolve(sds, case.call)(*case.args, **case.kwargs)
    _check(case, route, result)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
async def test_async(case: Case, asds: AsyncStellarDS, mock: respx.MockRouter) -> None:
    route = mock.route(method=case.method, path=case.path).mock(return_value=ok(case.data))
    result = await _resolve(asds, case.call)(*case.args, **case.kwargs)
    _check(case, route, result)


def test_every_public_method_is_covered() -> None:
    covered = {c.call for c in CASES}
    covered |= {
        "records.query",
        "records.iter",
        "records.get",
        "records.create",
        "records.update",
        "records.delete",
        "records.delete_many",
        "records.clear",
        "records.download_blob",
        "records.upload_blob",
        "query.execute",
        "oauth.exchange_code",
        "oauth.refresh",
        "oauth.revoke",
    }
    client = StellarDS("t", project=PROJECT)
    try:
        public = {
            f"{resource}.{name}"
            for resource, value in vars(client).items()
            if not resource.startswith("_")
            for name, _ in inspect.getmembers(value, inspect.ismethod)
            if not name.startswith("_")
        }
    finally:
        client.close()
    assert public - covered == set()


def test_updates_fill_in_current_values(sds: StellarDS, mock: respx.MockRouter) -> None:
    mock.get("/v1/schema/table").mock(
        return_value=ok({"id": 5, "name": "Orders", "description": "d", "isMultitenant": True})
    )
    put = mock.put("/v1/schema/table").mock(return_value=ok({"id": 5}))
    sds.tables.update(5, description="new")
    assert json.loads(put.calls.last.request.content) == {"name": "Orders", "description": "new", "isMultitenant": True}

    mock.get("/v1/webhooks/2").mock(
        return_value=ok({"id": 2, "url": "https://a", "events": ["record.created"], "tableIds": [5], "isActive": True})
    )
    hook_put = mock.put("/v1/webhooks/2").mock(return_value=ok({"id": 2}))
    sds.webhooks.update(2, is_active=False)
    assert json.loads(hook_put.calls.last.request.content) == {
        "url": "https://a",
        "events": ["record.created"],
        "tableIds": [5],
        "isActive": False,
    }

    mock.get("/v1/schema/table/field").mock(return_value=ok({"id": 9, "name": "price", "type": "Decimal(10,2)"}))
    field_put = mock.put("/v1/schema/table/field").mock(return_value=ok({"id": 9}))
    sds.fields.update(5, 9, name="amount")
    assert json.loads(field_put.calls.last.request.content) == {"name": "amount", "type": "Decimal(10,2)"}


async def test_async_update_fills_in_current_values(asds: AsyncStellarDS, mock: respx.MockRouter) -> None:
    mock.get("/v1/schema/project").mock(
        return_value=ok({"id": PROJECT, "name": "P", "description": "", "isMultitenant": False, "allowNewUsers": True})
    )
    put = mock.put("/v1/schema/project").mock(return_value=ok({"id": PROJECT, "name": "Q"}))
    project = await asds.projects.update(name="Q")
    assert project.name == "Q"
    assert json.loads(put.calls.last.request.content) == {
        "name": "Q",
        "description": "",
        "isMultitenant": False,
        "allowNewUsers": True,
    }


def test_oauth_exchange_code_via_client(mock: respx.MockRouter) -> None:
    from urllib.parse import parse_qs

    from stellards import OAuthCredentials

    route = mock.post("/v1/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "expires_in": 100})
    )
    creds = OAuthCredentials("cid", "csecret", "r0", access_token="x")
    with StellarDS(oauth=creds, base_url="https://api.test.stellards.io") as client:
        tokens = client.oauth.exchange_code("the-code", "https://app/cb")
        assert client.access_token == "x"  # exchanging doesn't change the client's own tokens
    assert tokens.access_token == "a"
    assert {k: v[0] for k, v in parse_qs(route.calls.last.request.content.decode()).items()} == {
        "grant_type": "authorization_code",
        "client_id": "cid",
        "client_secret": "csecret",
        "code": "the-code",
        "redirect_uri": "https://app/cb",
    }


def test_path_values_are_url_encoded(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.get(path__startswith="/v1/procedures/").mock(return_value=ok({"name": "monthly/report?"}))
    sds.procedures.get("monthly/report?")
    assert route.calls.last.request.url.raw_path.startswith(b"/v1/procedures/monthly%2Freport%3F?")
