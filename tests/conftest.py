"""Pytest configuration file for Boxarr tests."""

import json
import sys
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# Add src directory to Python path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(src_path))


@pytest.fixture
def app():
    """Create a fresh FastAPI app instance per test function."""
    from src.api.app import create_app

    return create_app()


@pytest.fixture
def client(app) -> Generator:
    """HTTP test client with lifespan events (startup/shutdown) executed."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Redirect all data-directory I/O to a fresh tmp_path per test."""
    import src.utils.config as config_module
    from src.utils.config import settings

    monkeypatch.setattr(settings, "boxarr_data_directory", tmp_path)
    monkeypatch.setenv("BOXARR_DATA_DIRECTORY", str(tmp_path))
    yield tmp_path
    # Clear singleton so any reload_from_file side-effect doesn't bleed into
    # the next test. monkeypatch.undo() (which runs after this) will recreate
    # _settings from the restored env, giving the next test a clean slate.
    config_module._settings = None


@pytest.fixture
def weekly_json(isolated_data_dir) -> Path:
    """Write a minimal valid weekly JSON fixture and return its path."""
    weekly_dir = isolated_data_dir / "weekly_pages"
    weekly_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "year": 2025,
        "week": 1,
        "movies": [
            {
                "rank": 1,
                "title": "Inception",
                "tmdb_id": 27205,
                "radarr_id": 101,
                "status": "Downloaded",
                "weekend_gross": 62785337,
                "poster": "https://example.com/poster.jpg",
                "year": 2010,
            },
            {
                "rank": 2,
                "title": "Unknown Film",
                "tmdb_id": None,
                "radarr_id": None,
                "status": "Missing",
                "weekend_gross": 10000000,
                "poster": None,
                "year": 2025,
            },
        ],
    }
    path = weekly_dir / "202501.json"
    path.write_text(json.dumps(data))
    return path
