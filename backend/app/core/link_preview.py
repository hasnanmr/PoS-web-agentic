"""Link preview (Open Graph) for the outlet link `/o/<slug>` — page 07, "Pratinjau link outlet".

When an owner pastes the outlet link into WhatsApp, a WhatsApp status, an Instagram DM, Facebook
or Telegram, the app fetches the page and shows a card. The chat page is a client-side app, so the
admin nginx sends those preview bots (and only them) to `GET /api/v1/public/o/{slug}/share`,
which answers with this small HTML page. People always get the chat itself.

Copy (canvas note "Catatan perilaku · Bagikan link outlet"): the title is
"Pesan di <Nama outlet> · Thinker"; the description follows what the outlet offers; the image is
the same for every outlet (`admin/public/og-outlet.png`, 1200x630, drawn on page 07). An unknown or
old slug gets the generic "Thinker" card without any outlet data.
"""

from __future__ import annotations

from html import escape

SITE_NAME = "Thinker"
IMAGE_PATH = "/og-outlet.png"
IMAGE_WIDTH = 1200
IMAGE_HEIGHT = 630
GENERIC_TITLE = "Thinker"
GENERIC_DESCRIPTION = "Pesan langsung lewat chat. Bayar pakai QRIS, tanpa daftar."


def outlet_title(outlet_name: str) -> str:
    return f"Pesan di {outlet_name} · {SITE_NAME}"


def outlet_description(*, web_ordering: bool, reservations_enabled: bool) -> str:
    """The four descriptions on the canvas note: online orders need the outlet's static QRIS."""
    if web_ordering and reservations_enabled:
        return (
            "Pesan online, lihat rekomendasi, dan reservasi meja. Bayar pakai QRIS, tanpa daftar."
        )
    if web_ordering:
        return "Pesan online dan lihat rekomendasi. Bayar pakai QRIS, tanpa daftar."
    if reservations_enabled:
        return "Lihat menu, rekomendasi, dan reservasi meja. Pesanan dilayani di kasir."
    return "Lihat menu dan rekomendasi. Pesanan dilayani di kasir."


def render(*, title: str, description: str, app_url: str | None, slug: str | None) -> str:
    """The preview page. Without `ADMIN_APP_URL` the absolute URL and image are left out (Open
    Graph needs absolute URLs); the title and description still show."""
    base = app_url.rstrip("/") if app_url else None
    page_url = f"{base}/o/{slug}" if base and slug else base
    meta = [
        ("property", "og:type", "website"),
        ("property", "og:site_name", SITE_NAME),
        ("property", "og:locale", "id_ID"),
        ("property", "og:title", title),
        ("property", "og:description", description),
        ("name", "description", description),
        ("name", "twitter:title", title),
        ("name", "twitter:description", description),
    ]
    if page_url:
        meta.append(("property", "og:url", page_url))
    if base:
        image = f"{base}{IMAGE_PATH}"
        meta += [
            ("property", "og:image", image),
            ("property", "og:image:secure_url", image),
            ("property", "og:image:type", "image/png"),
            ("property", "og:image:width", str(IMAGE_WIDTH)),
            ("property", "og:image:height", str(IMAGE_HEIGHT)),
            ("property", "og:image:alt", f"{SITE_NAME} · pesan langsung lewat chat"),
            ("name", "twitter:card", "summary_large_image"),
            ("name", "twitter:image", image),
        ]
    tags = "\n".join(f'    <meta {k}="{escape(n)}" content="{escape(v)}" />' for k, n, v in meta)
    canonical = f'    <link rel="canonical" href="{escape(page_url)}" />\n' if page_url else ""
    link = f'<a href="{escape(page_url)}">{escape(title)}</a>' if page_url else escape(title)
    return (
        "<!doctype html>\n"
        '<html lang="id">\n'
        "  <head>\n"
        '    <meta charset="utf-8" />\n'
        f"    <title>{escape(title)}</title>\n"
        f"{tags}\n"
        f"{canonical}"
        "  </head>\n"
        f"  <body><p>{link}</p><p>{escape(description)}</p></body>\n"
        "</html>\n"
    )
