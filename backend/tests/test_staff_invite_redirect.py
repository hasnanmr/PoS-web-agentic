"""O4 invite links land on the staff area of the admin app (`/admin`)."""

from types import SimpleNamespace

import pytest

from app.api.v1.owner.staff import _redirect


def _request(admin_app_url: str | None) -> SimpleNamespace:
    settings = SimpleNamespace(admin_app_url=admin_app_url)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("https://admin.example.com", "https://admin.example.com/admin"),
        ("https://admin.example.com/", "https://admin.example.com/admin"),
        ("https://admin.example.com/admin", "https://admin.example.com/admin"),
        ("https://admin.example.com/admin/", "https://admin.example.com/admin"),
    ],
)
def test_redirect_points_to_staff_area_once(configured: str, expected: str) -> None:
    assert _redirect(_request(configured)) == expected  # type: ignore[arg-type]


def test_no_redirect_without_admin_app_url() -> None:
    assert _redirect(_request(None)) is None  # type: ignore[arg-type]
