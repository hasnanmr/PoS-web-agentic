"""Link preview page for the outlet link (page 07, "Pratinjau link outlet")."""

from __future__ import annotations

from app.core import link_preview


def test_description_follows_what_the_outlet_offers() -> None:
    d = link_preview.outlet_description
    assert d(web_ordering=True, reservations_enabled=True).startswith("Pesan online, lihat")
    assert d(web_ordering=True, reservations_enabled=False).startswith("Pesan online dan")
    assert d(web_ordering=False, reservations_enabled=True).endswith("dilayani di kasir.")
    assert d(web_ordering=False, reservations_enabled=False) == (
        "Lihat menu dan rekomendasi. Pesanan dilayani di kasir."
    )


def test_outlet_name_is_escaped() -> None:
    page = link_preview.render(
        title=link_preview.outlet_title('Kopi "Senja" <b>&</b>'),
        description="x",
        app_url="https://pesan.example/",
        slug="kopi-senja",
    )
    assert "<b>" not in page
    assert 'content="Pesan di Kopi &quot;Senja&quot; &lt;b&gt;&amp;&lt;/b&gt; · Thinker"' in page
    assert 'content="https://pesan.example/o/kopi-senja"' in page
    assert 'content="https://pesan.example/og-outlet.png"' in page


def test_without_app_url_there_is_no_image_or_url() -> None:
    page = link_preview.render(title="T", description="D", app_url=None, slug="kopi")
    assert "og:image" not in page and "og:url" not in page and "canonical" not in page
    assert '<meta property="og:title" content="T" />' in page
