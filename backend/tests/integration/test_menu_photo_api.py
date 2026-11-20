"""Menu photos (T-132) against Postgres through RLS, with a fake Storage: upload and
replace from O5, signed URLs in O5 and the counter menu (S1), size and type checks, the
required-photo rule before an item can be active, owner only.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import StorageError

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "o5photo.test"
OWNER = UUID("50000000-0000-0000-0000-0000000005f0")
STAFF = UUID("50000000-0000-0000-0000-0000000005f1")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.removed: list[str] = []
        self.signed: list[str] = []
        self.fail_upload = False
        self.fail_sign = False

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        if self.fail_upload:
            raise StorageError(500, "boom")
        assert (bucket, path) not in self.objects  # never overwrites
        self.objects[(bucket, path)] = (data, content_type)

    def signed_urls(self, bucket: str, paths: list[str], expires_in: int) -> dict[str, str]:
        assert expires_in == 3600
        if self.fail_sign:
            raise StorageError(0, "TimeoutError: timed out")
        self.signed.extend(paths)
        return {p: f"https://signed.test/{bucket}/{p}?token=t" for p in paths}

    def remove(self, bucket: str, paths: list[str]) -> None:
        self.removed.extend(paths)
        for p in paths:
            self.objects.pop((bucket, p), None)


def _bearer(sub: UUID, tenant: str | None, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=str(sub), tenant_id=tenant, app_role=role)}"}


@pytest.fixture(scope="module")
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture(scope="module")
def client(storage: FakeStorage) -> Iterator[TestClient]:
    cleanup_domain(DOMAIN)
    invite_owner(OWNER, f"owner@{DOMAIN}")
    app = create_app(
        Settings(database_url=APP_URL), token_verifier=make_verifier(), storage=storage
    )
    with TestClient(app) as c:
        yield c
    cleanup_domain(DOMAIN)


@pytest.fixture(scope="module")
def ctx(client: TestClient) -> dict[str, Any]:
    res = client.post(
        "/api/v1/owner/onboarding",
        headers=_bearer(OWNER, None, "owner_pending"),
        json={"business": {"name": "Kopi Foto", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, outlet = res.json()["tenant_id"], res.json()["outlet_id"]
    admin_sql("insert into auth.users (id, email) values (%s, %s)", (STAFF, f"rina@{DOMAIN}"))
    admin_sql(
        "insert into app.users (id, tenant_id, email, display_name, role,"
        " invitation_accepted_at) values (%s, %s, %s, 'Rina', 'staff', now())",
        (STAFF, tenant, f"rina@{DOMAIN}"),
    )
    admin_sql(
        "insert into app.staff_outlets (user_id, outlet_id, tenant_id) values (%s, %s, %s)",
        (STAFF, outlet, tenant),
    )
    owner = _bearer(OWNER, tenant, "owner")
    sample = next(
        p
        for p in client.get("/api/v1/owner/products", headers=owner).json()
        if p["name"] == "Americano"
    )
    return {
        "tenant": tenant,
        "outlet": outlet,
        "owner": owner,
        "staff": _bearer(STAFF, tenant, "staff"),
        "americano": sample["id"],
    }


def _put(client: TestClient, ctx: dict[str, Any], pid: str, data: bytes, kind: str) -> Any:
    return client.put(
        f"/api/v1/owner/products/{pid}/photo",
        headers={**ctx["owner"], "Content-Type": kind},
        content=data,
    )


def test_new_item_starts_inactive_and_needs_a_photo_to_go_live(client, ctx, storage) -> None:
    res = client.post(
        "/api/v1/owner/products",
        headers=ctx["owner"],
        json={"name": "Kopi Gula Aren", "is_active": True},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "photo_required"

    res = client.post("/api/v1/owner/products", headers=ctx["owner"], json={"name": "Es Teh"})
    assert res.status_code == 201, res.text
    teh = res.json()
    assert (teh["is_active"], teh["has_photo"], teh["photo_url"]) == (False, False, None)
    url = f"/api/v1/owner/products/{teh['id']}"
    res = client.patch(url, headers=ctx["owner"], json={"is_active": True})
    assert res.status_code == 422 and res.json()["error"]["code"] == "photo_required"

    res = _put(client, ctx, teh["id"], PNG, "image/png")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["has_photo"] is True
    path = body["photo_url"].split("/menu-photos/")[1].split("?")[0]
    assert path.startswith(f"{ctx['tenant']}/{teh['id']}/") and path.endswith(".png")
    assert storage.objects[("menu-photos", path)] == (PNG, "image/png")

    res = client.patch(url, headers=ctx["owner"], json={"is_active": True})
    assert res.status_code == 200 and res.json()["is_active"] is True
    audit = admin_sql(
        "select action from app.audit_events where entity_id = %s order by id", (teh["id"],)
    )
    assert ("product.photo_updated",) in audit


def test_replace_removes_old_object_and_urls_reach_o5_and_counter(client, ctx, storage) -> None:
    pid = ctx["americano"]
    # The sample item is active without a photo (FR2.12): still editable.
    res = client.patch(
        f"/api/v1/owner/products/{pid}", headers=ctx["owner"], json={"description": "Hitam"}
    )
    assert res.status_code == 200, res.text
    first = _put(client, ctx, pid, JPG, "image/jpeg").json()["photo_url"]
    second = _put(client, ctx, pid, WEBP, "image/webp").json()
    assert second["photo_url"] != first and second["photo_url"].endswith(".webp?token=t")
    old_path = first.split("/menu-photos/")[1].split("?")[0]
    assert old_path in storage.removed
    assert ("menu-photos", old_path) not in storage.objects
    assert second["is_sample"] is False

    rows = client.get("/api/v1/owner/products", headers=ctx["owner"]).json()
    row = next(r for r in rows if r["id"] == pid)
    assert row["photo_url"] == second["photo_url"] and row["has_photo"] is True
    assert all(r["photo_url"] is None for r in rows if not r["has_photo"])
    menu = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/menu", headers=ctx["staff"]).json()
    item = next(m for m in menu if m["product_id"] == pid)
    assert item["photo_url"] == second["photo_url"]


def test_rejects_bad_files_staff_unknown_items_and_storage_failures(client, ctx, storage) -> None:
    pid = ctx["americano"]
    before = admin_sql("select photo_path from app.products where id = %s", (pid,))[0][0]
    res = _put(client, ctx, pid, b"GIF89a" + b"\x00" * 10, "image/gif")
    assert res.status_code == 422 and res.json()["error"]["details"] == {"field": "photo"}
    res = _put(client, ctx, pid, JPG, "image/png")  # renamed file
    assert res.status_code == 422
    res = _put(client, ctx, pid, PNG + b"\x00" * (5 * 1024 * 1024), "image/png")
    assert res.status_code == 422
    res = client.put(
        f"/api/v1/owner/products/{pid}/photo",
        headers={**ctx["staff"], "Content-Type": "image/png"},
        content=PNG,
    )
    assert res.status_code == 403
    other = "00000000-0000-0000-0000-000000000099"
    assert _put(client, ctx, other, PNG, "image/png").status_code == 404

    storage.fail_upload = True
    try:
        res = _put(client, ctx, pid, PNG, "image/png")
    finally:
        storage.fail_upload = False
    assert res.status_code == 502 and res.json()["error"]["code"] == "storage_failed"
    after = admin_sql("select photo_path from app.products where id = %s", (pid,))[0][0]
    assert after == before


def test_signed_urls_are_reused_and_storage_failures_degrade(client, ctx, storage) -> None:
    menu_url = f"/api/v1/ops/outlets/{ctx['outlet']}/menu"
    first = {
        m["product_id"]: m["photo_url"] for m in client.get(menu_url, headers=ctx["staff"]).json()
    }
    signed = len(storage.signed)
    again = {
        m["product_id"]: m["photo_url"] for m in client.get(menu_url, headers=ctx["staff"]).json()
    }
    assert again == first and len(storage.signed) == signed  # cached: same URL, no new signing

    # A new photo (new path) must be signed; if Storage fails, the menu still loads.
    pid = ctx["americano"]
    storage.fail_sign = True
    try:
        res = _put(client, ctx, pid, PNG, "image/png")
        assert res.status_code == 200 and res.json()["photo_url"] is None
        menu = client.get(menu_url, headers=ctx["staff"])
        assert menu.status_code == 200
        assert next(m for m in menu.json() if m["product_id"] == pid)["photo_url"] is None
    finally:
        storage.fail_sign = False


def test_chunked_upload_is_cut_off_at_5_mb(client, ctx) -> None:
    def chunks() -> Iterator[bytes]:
        yield PNG
        for _ in range(6):
            yield b"\x00" * (1024 * 1024)

    res = client.put(
        f"/api/v1/owner/products/{ctx['americano']}/photo",
        headers={**ctx["owner"], "Content-Type": "image/png"},
        content=chunks(),
    )
    assert res.status_code == 422 and res.json()["error"]["details"] == {"field": "photo"}


def test_deleting_an_unordered_item_removes_its_photo(client, ctx, storage) -> None:
    res = client.post("/api/v1/owner/products", headers=ctx["owner"], json={"name": "Bolu"})
    pid = res.json()["id"]
    url = _put(client, ctx, pid, JPG, "image/jpeg").json()["photo_url"]
    path = url.split("/menu-photos/")[1].split("?")[0]
    res = client.delete(f"/api/v1/owner/products/{pid}", headers=ctx["owner"])
    assert res.json() == {"result": "deleted"}
    assert path in storage.removed and ("menu-photos", path) not in storage.objects


def test_upload_without_storage_configured_is_503(ctx) -> None:
    app = create_app(Settings(database_url=APP_URL), token_verifier=make_verifier())
    app.state.storage = None
    with TestClient(app) as c:
        res = c.put(
            f"/api/v1/owner/products/{ctx['americano']}/photo",
            headers={**ctx["owner"], "Content-Type": "image/png"},
            content=PNG,
        )
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "storage_not_configured"
        # Lists still work; photos just have no URL.
        rows = c.get("/api/v1/owner/products", headers=ctx["owner"]).json()
        assert all(r["photo_url"] is None for r in rows)
