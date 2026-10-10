import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
KIT = ROOT / "build-the-builder-v3" / "build-the-builder"


@pytest.fixture(scope="session")
def kit() -> pathlib.Path:
    """The organisers' kit folder. Tests that compare against it skip when it is missing."""
    if not KIT.exists():
        pytest.skip("kit folder not found")
    return KIT


@pytest.fixture
def kit_api(kit: pathlib.Path) -> dict:
    """The practice tool API file, as a dict."""
    return json.loads((kit / "tools" / "openapi.json").read_text(encoding="utf-8"))
