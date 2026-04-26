"""Tests for src/core/radarr.py - RadarrService."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.core.exceptions import (
    RadarrAuthenticationError,
    RadarrConnectionError,
    RadarrError,
    RadarrNotFoundError,
)
from src.core.models import MovieStatus
from src.core.radarr import (
    QualityProfile,
    RadarrMovie,
    RadarrService,
    get_all_movies_with_optional_cache_bypass,
)
from src.utils.config import settings


def _make_mock_response(status_code=200, data=None, text=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    if data is not None:
        resp.json.return_value = data
    if text is not None:
        resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


def _make_service(response_or_map=None, monkeypatch=None):
    """Create RadarrService with mocked HTTP client."""
    client = MagicMock(spec=httpx.Client)
    if isinstance(response_or_map, dict):
        # Map of endpoint -> response
        def _request(method, endpoint, **kwargs):
            return response_or_map.get(endpoint, _make_mock_response(200, []))

        client.request = _request
    elif response_or_map is not None:
        client.request.return_value = response_or_map
    svc = RadarrService(
        url="http://localhost:7878", api_key="testkey", http_client=client
    )
    return svc, client


class TestRadarrServiceInit:
    def test_no_api_key_raises(self):
        with pytest.raises(RadarrAuthenticationError):
            RadarrService(url="http://localhost:7878", api_key="")

    def test_init_with_key(self):
        client = MagicMock(spec=httpx.Client)
        svc = RadarrService(
            url="http://localhost:7878", api_key="key", http_client=client
        )
        assert svc.api_key == "key"

    def test_context_manager(self):
        client = MagicMock(spec=httpx.Client)
        with RadarrService(
            url="http://localhost:7878", api_key="key", http_client=client
        ) as svc:
            assert svc is not None
        client.close.assert_called_once()


class TestMakeRequest:
    def test_401_raises_auth_error(self):
        svc, client = _make_service()
        resp = _make_mock_response(401)
        resp.raise_for_status = MagicMock()
        client.request.return_value = resp
        with pytest.raises(RadarrAuthenticationError):
            svc._make_request("GET", "/api/v3/test")

    def test_404_raises_not_found(self):
        svc, client = _make_service()
        resp = _make_mock_response(404)
        client.request.return_value = resp
        with pytest.raises(RadarrNotFoundError):
            svc._make_request("GET", "/api/v3/missing")

    def test_connect_error_raises_connection_error(self):
        svc, client = _make_service()
        client.request.side_effect = httpx.ConnectError("connection refused")
        with pytest.raises(RadarrConnectionError):
            svc._make_request("GET", "/api/v3/test")

    def test_http_error_raises_radarr_error(self):
        svc, client = _make_service()
        err = httpx.HTTPStatusError("error", request=MagicMock(), response=MagicMock())
        err.response.status_code = 500
        err.response.json.return_value = {"message": "Internal server error"}
        client.request.side_effect = err
        with pytest.raises(RadarrError):
            svc._make_request("GET", "/api/v3/test")

    def test_success_returns_response(self):
        resp = _make_mock_response(200, [])
        svc, client = _make_service(resp)
        result = svc._make_request("GET", "/api/v3/test")
        assert result.status_code == 200


class TestTestConnection:
    def test_success_returns_true(self):
        resp = _make_mock_response(200, {"version": "4.0"})
        svc, client = _make_service(resp)
        assert svc.test_connection() is True

    def test_radarr_error_returns_false(self):
        svc, client = _make_service()
        client.request.side_effect = httpx.ConnectError("refused")
        assert svc.test_connection() is False


class TestGetAllMovies:
    def test_returns_movie_list(self, monkeypatch):
        # Clear cache first
        import src.core.radarr as radarr_module

        radarr_module._movies_cache["data"] = []
        radarr_module._movies_cache["ts"] = 0.0

        movie_data = [
            {
                "id": 1,
                "title": "Inception",
                "tmdbId": 27205,
                "monitored": True,
                "hasFile": False,
                "isAvailable": False,
                "status": "released",
                "images": [],
                "genres": [],
                "year": 2010,
            }
        ]
        resp = _make_mock_response(200, movie_data)
        svc, _ = _make_service(resp)
        movies = svc.get_all_movies(ignore_cache=True)
        assert len(movies) == 1
        assert movies[0].title == "Inception"

    def test_uses_cache(self):
        import time

        import src.core.radarr as radarr_module

        fake_movie = MagicMock(spec=RadarrMovie)
        radarr_module._movies_cache["data"] = [fake_movie]
        radarr_module._movies_cache["ts"] = time.time()
        svc, client = _make_service()
        result = svc.get_all_movies(ignore_cache=False)
        client.request.assert_not_called()
        assert result == [fake_movie]


class TestSearchMovie:
    def test_returns_list(self):
        results = [{"tmdbId": 1, "title": "Test"}]
        resp = _make_mock_response(200, results)
        svc, _ = _make_service(resp)
        assert svc.search_movie("test") == results

    def test_non_list_response_returns_empty(self):
        resp = _make_mock_response(200, {"error": "bad"})
        svc, _ = _make_service(resp)
        assert svc.search_movie("test") == []


class TestGetQualityProfiles:
    def test_returns_profiles(self):
        import src.core.radarr as radarr_module

        radarr_module._profiles_cache["data"] = []
        radarr_module._profiles_cache["ts"] = 0.0

        profiles_data = [
            {
                "id": 1,
                "name": "HD-1080p",
                "upgradeAllowed": True,
                "cutoff": 1,
                "items": [],
            }
        ]
        resp = _make_mock_response(200, profiles_data)
        svc, _ = _make_service(resp)
        profiles = svc.get_quality_profiles(ignore_cache=True)
        assert len(profiles) == 1
        assert profiles[0].name == "HD-1080p"


class TestGetMovie:
    def test_returns_movie(self):
        movie_data = {
            "id": 5,
            "title": "The Matrix",
            "tmdbId": 603,
            "monitored": True,
            "hasFile": True,
            "isAvailable": True,
            "status": "released",
            "images": [],
            "genres": [],
            "year": 1999,
        }
        resp = _make_mock_response(200, movie_data)
        svc, _ = _make_service(resp)
        movie = svc.get_movie(5)
        assert movie.title == "The Matrix"
        assert movie.hasFile is True


class TestGetAllMoviesWithCacheBypass:
    def test_bypass_when_method_supports_it(self):
        calls = []

        class _FakeSvc:
            def get_all_movies(self, ignore_cache: bool = False):
                calls.append(ignore_cache)
                return []

        result = get_all_movies_with_optional_cache_bypass(
            _FakeSvc(), ignore_cache=True
        )
        assert calls == [True]

    def test_no_bypass_calls_without_param(self):
        calls = []

        class _FakeSvc:
            def get_all_movies(self, ignore_cache: bool = False):
                calls.append(ignore_cache)
                return []

        result = get_all_movies_with_optional_cache_bypass(
            _FakeSvc(), ignore_cache=False
        )
        assert calls == [False]

    def test_service_without_param_still_calls(self):
        """If the method doesn't accept ignore_cache, still calls without it."""
        calls = []

        class _SimpleSvc:
            def get_all_movies(self):
                calls.append(True)
                return []

        result = get_all_movies_with_optional_cache_bypass(
            _SimpleSvc(), ignore_cache=True
        )
        assert calls == [True]


class TestRadarrMovieProperties:
    def _make_movie(self, **kwargs):
        defaults = {"id": 1, "title": "Test", "tmdbId": 100}
        defaults.update(kwargs)
        return RadarrMovie(**defaults)

    def test_poster_url_from_images(self):
        movie = self._make_movie(
            images=[{"coverType": "poster", "remoteUrl": "https://img.jpg"}]
        )
        assert movie.poster_url == "https://img.jpg"

    def test_poster_url_no_poster_image(self):
        movie = self._make_movie(
            images=[{"coverType": "fanart", "remoteUrl": "https://img.jpg"}]
        )
        assert movie.poster_url is None

    def test_poster_url_empty_images(self):
        movie = self._make_movie(images=[])
        assert movie.poster_url is None

    def test_file_quality(self):
        movie = self._make_movie(
            movieFile={
                "quality": {"quality": {"name": "Bluray-1080p"}},
                "size": 8000000000,
            }
        )
        assert movie.file_quality == "Bluray-1080p"

    def test_file_quality_no_file(self):
        movie = self._make_movie()
        assert movie.file_quality is None

    def test_file_size_gb(self):
        movie = self._make_movie(movieFile={"size": 2 * 1024**3, "quality": {}})
        assert movie.file_size_gb == 2.0

    def test_file_size_gb_no_file(self):
        movie = self._make_movie()
        assert movie.file_size_gb is None


class TestTagManagement:
    def test_get_tags_returns_list(self):
        resp = _make_mock_response(200, [{"id": 1, "label": "action"}])
        svc, _ = _make_service(resp)
        tags = svc.get_tags()
        assert len(tags) == 1

    def test_get_tag_by_label_found(self):
        resp = _make_mock_response(200, [{"id": 1, "label": "action"}])
        svc, _ = _make_service(resp)
        tag = svc.get_tag_by_label("Action")
        assert tag["id"] == 1

    def test_get_tag_by_label_not_found(self):
        resp = _make_mock_response(200, [{"id": 1, "label": "drama"}])
        svc, _ = _make_service(resp)
        tag = svc.get_tag_by_label("comedy")
        assert tag is None

    def test_create_tag_returns_int_id(self):
        resp = _make_mock_response(200, {"id": 5, "label": "boxarr"})
        svc, _ = _make_service(resp)
        tag_id = svc.create_tag("boxarr")
        assert tag_id == 5

    def test_create_tag_string_id_cast(self):
        resp = _make_mock_response(200, {"id": "7", "label": "boxarr"})
        svc, _ = _make_service(resp)
        tag_id = svc.create_tag("boxarr")
        assert tag_id == 7

    def test_create_tag_non_dict_returns_none(self):
        resp = _make_mock_response(200, [])
        svc, _ = _make_service(resp)
        tag_id = svc.create_tag("boxarr")
        assert tag_id is None

    def test_ensure_tag_creates_when_not_found(self):
        tags_resp = _make_mock_response(200, [])
        create_resp = _make_mock_response(200, {"id": 10, "label": "boxarr"})
        svc, client = _make_service()
        client.request.side_effect = [tags_resp, create_resp]
        tag_id = svc.ensure_tag("boxarr")
        assert tag_id == 10

    def test_ensure_tag_returns_existing(self):
        tags_resp = _make_mock_response(200, [{"id": 3, "label": "boxarr"}])
        svc, client = _make_service()
        client.request.return_value = tags_resp
        tag_id = svc.ensure_tag("boxarr")
        assert tag_id == 3

    def test_ensure_tag_create_raises_returns_none(self):
        svc, client = _make_service()
        # First call (get tags) returns empty, second call (create) raises
        tags_resp = _make_mock_response(200, [])
        client.request.side_effect = [tags_resp, Exception("create failed")]
        tag_id = svc.ensure_tag("boxarr")
        assert tag_id is None


class TestRadarrMoviePropertiesEdgeCases:
    def _make_movie(self, **kwargs):
        defaults = {"id": 1, "title": "Test", "tmdbId": 100}
        defaults.update(kwargs)
        return RadarrMovie(**defaults)

    def test_file_quality_non_dict_quality_obj_returns_none(self):
        """Covers the branch where quality_obj is not a dict."""
        movie = self._make_movie(
            movieFile={"quality": {"quality": "not-a-dict"}, "size": 1000}
        )
        assert movie.file_quality is None

    def test_file_quality_name_not_string_returns_none(self):
        movie = self._make_movie(
            movieFile={"quality": {"quality": {"name": 123}}, "size": 1000}
        )
        assert movie.file_quality is None

    def test_file_size_zero_returns_none(self):
        movie = self._make_movie(movieFile={"size": 0, "quality": {}})
        assert movie.file_size_gb is None


class TestAdditionalRadarrMethods:
    def test_get_system_status(self):
        resp = _make_mock_response(200, {"version": "4.0"})
        svc, _ = _make_service(resp)
        result = svc.get_system_status()
        assert result["version"] == "4.0"

    def test_get_system_status_non_dict_returns_empty(self):
        resp = _make_mock_response(200, [])
        svc, _ = _make_service(resp)
        resp.json.return_value = []
        result = svc.get_system_status()
        assert result == {}

    def test_get_root_folders(self):
        resp = _make_mock_response(200, [{"path": "/movies", "freeSpace": 100}])
        svc, _ = _make_service(resp)
        import src.core.radarr as radarr_module

        radarr_module._root_folders_cache["data"] = []
        radarr_module._root_folders_cache["ts"] = 0.0
        folders = svc.get_root_folders(ignore_cache=True)
        assert len(folders) == 1
        assert folders[0]["path"] == "/movies"

    def test_get_root_folder_paths(self):
        resp = _make_mock_response(200, [{"path": "/movies"}, {"path": "/anime"}])
        svc, _ = _make_service(resp)
        import src.core.radarr as radarr_module

        radarr_module._root_folders_cache["data"] = []
        radarr_module._root_folders_cache["ts"] = 0.0
        paths = svc.get_root_folder_paths()
        assert "/movies" in paths
        assert "/anime" in paths

    def test_get_quality_profile_by_name_found(self):
        import src.core.radarr as radarr_module

        radarr_module._profiles_cache["data"] = []
        radarr_module._profiles_cache["ts"] = 0.0

        resp = _make_mock_response(
            200,
            [
                {
                    "id": 1,
                    "name": "HD-1080p",
                    "upgradeAllowed": True,
                    "cutoff": 1,
                    "items": [],
                }
            ],
        )
        svc, _ = _make_service(resp)
        profile = svc.get_quality_profile_by_name("hd-1080p")
        assert profile is not None
        assert profile.name == "HD-1080p"

    def test_get_quality_profile_by_name_not_found(self):
        import src.core.radarr as radarr_module

        radarr_module._profiles_cache["data"] = []
        radarr_module._profiles_cache["ts"] = 0.0

        resp = _make_mock_response(
            200,
            [
                {
                    "id": 1,
                    "name": "HD-1080p",
                    "upgradeAllowed": True,
                    "cutoff": 1,
                    "items": [],
                }
            ],
        )
        svc, _ = _make_service(resp)
        profile = svc.get_quality_profile_by_name("Ultra-HD")
        assert profile is None

    def test_search_movie_by_title_exact_match(self):
        """Covers search_movie_by_title exact match branch."""
        import src.core.radarr as radarr_module

        radarr_module._movies_cache["data"] = []
        radarr_module._movies_cache["ts"] = 0.0

        movie_data = [
            {
                "id": 1,
                "title": "Inception",
                "tmdbId": 27205,
                "monitored": True,
                "hasFile": False,
                "isAvailable": False,
                "status": "released",
                "images": [],
                "genres": [],
                "year": 2010,
            }
        ]
        resp = _make_mock_response(200, movie_data)
        svc, _ = _make_service(resp)
        result = svc.search_movie_by_title("Inception")
        assert result is not None
        assert result.title == "Inception"

    def test_search_movie_by_title_partial_match(self):
        import src.core.radarr as radarr_module

        radarr_module._movies_cache["data"] = []
        radarr_module._movies_cache["ts"] = 0.0

        movie_data = [
            {
                "id": 1,
                "title": "Inception Part 2",
                "tmdbId": 27205,
                "monitored": True,
                "hasFile": False,
                "isAvailable": False,
                "status": "released",
                "images": [],
                "genres": [],
                "year": 2010,
            }
        ]
        resp = _make_mock_response(200, movie_data)
        svc, _ = _make_service(resp)
        result = svc.search_movie_by_title("Inception")
        assert result is not None

    def test_search_movie_by_title_not_found(self):
        import src.core.radarr as radarr_module

        radarr_module._movies_cache["data"] = []
        radarr_module._movies_cache["ts"] = 0.0

        resp = _make_mock_response(
            200,
            [
                {
                    "id": 1,
                    "title": "Avatar",
                    "tmdbId": 19995,
                    "monitored": True,
                    "hasFile": False,
                    "isAvailable": False,
                    "status": "released",
                    "images": [],
                    "genres": [],
                    "year": 2009,
                }
            ],
        )
        svc, _ = _make_service(resp)
        result = svc.search_movie_by_title("Inception")
        assert result is None

    def test_trigger_movie_search_success(self):
        resp = _make_mock_response(200, {"status": "queued"})
        svc, _ = _make_service(resp)
        result = svc.trigger_movie_search(1)
        assert result is True

    def test_trigger_movie_search_failure(self):
        svc, client = _make_service()
        client.request.side_effect = Exception("search failed")
        result = svc.trigger_movie_search(1)
        assert result is False

    def test_make_request_unexpected_exception(self):
        """Covers the generic except branch in _make_request."""
        svc, client = _make_service()
        client.request.side_effect = OSError("socket error")
        from src.core.exceptions import RadarrError

        with pytest.raises(RadarrError):
            svc._make_request("GET", "/api/v3/test")

    def test_make_request_http_status_error_errors_field(self):
        """Covers the 'errors' field in JSON body branch."""
        svc, client = _make_service()
        err = httpx.HTTPStatusError("error", request=MagicMock(), response=MagicMock())
        err.response.status_code = 500
        err.response.json.return_value = {"errors": ["err1", "err2"]}
        client.request.side_effect = err
        from src.core.exceptions import RadarrError

        with pytest.raises(RadarrError):
            svc._make_request("GET", "/api/v3/test")

    def test_close_when_no_client(self):
        """Covers the `if self.client` branch in close()."""
        client = MagicMock(spec=httpx.Client)
        svc = RadarrService(
            url="http://localhost:7878", api_key="key", http_client=client
        )
        svc.client = None
        svc.close()  # Should not raise

    def test_root_folders_cache_hit(self):
        """Covers the cache hit branch for root folders."""
        import time

        import src.core.radarr as radarr_module

        radarr_module._root_folders_cache["data"] = [{"path": "/cached"}]
        radarr_module._root_folders_cache["ts"] = time.time()
        svc, client = _make_service()
        result = svc.get_root_folders(ignore_cache=False)
        client.request.assert_not_called()
        assert result[0]["path"] == "/cached"
