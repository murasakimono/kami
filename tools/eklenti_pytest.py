"""tools.eklenti_test'in pytest eki: `plugin` fiksturu + network isareti (--ag ile calisir)."""
from __future__ import annotations

import os

import pytest


def pytest_addoption(parser) -> None:
    parser.addoption("--ag", action="store_true", default=False, help="gercek ag testlerini de calistir")


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "network: gercek ag ister (--ag ile calisir)")


def pytest_collection_modifyitems(config, items) -> None:
    if config.getoption("--ag"):
        return
    skip = pytest.mark.skip(reason="ag testi: --ag ile calistir")
    for it in items:
        if "network" in it.keywords:
            it.add_marker(skip)


@pytest.fixture
def plugin():
    from tools.eklenti_test import Loaded, load_one
    pid = os.environ.get("KAMI_PLUGIN_ID", "")
    info, reg = load_one(pid)
    assert info is not None and not info.error, info.error if info else f"{pid} bulunamadi"
    return Loaded(info, reg)
