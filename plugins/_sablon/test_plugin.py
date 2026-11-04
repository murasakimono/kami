"""__NAME__ eklenti testi. Calistir: uv run python -m tools.eklenti_test __ID__
Ag gerektiren testleri @pytest.mark.network ile isaretle (varsayilan kosuda atlanir; --ag ile calisir)."""
import pytest


def test_desenler(plugin):
    assert plugin.matches("https://ornek.com/f/abc123")
    assert not plugin.matches("https://ornek.com/hakkinda")


@pytest.mark.network
def test_gercek_link(plugin):
    listing = plugin.cloud.list("https://ornek.com/f/abc123")
    assert listing.files
