"""Tests for web UI routes (/, /setup, /overview, /dashboard, etc.)."""

import pytest

from src.utils.config import settings


class TestHomePage:
    def test_unconfigured_redirects_to_setup(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)
        assert "/setup" in resp.headers["location"]

    def test_configured_redirects_to_overview(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)
        assert "/overview" in resp.headers["location"]


class TestSettingsRedirect:
    def test_settings_redirects_to_setup(self, client):
        resp = client.get("/settings", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)
        assert "/setup" in resp.headers["location"]


class TestSetupPage:
    def test_setup_returns_200(self, client):
        resp = client.get("/setup")
        assert resp.status_code == 200
        assert b"html" in resp.content.lower()

    def test_setup_contains_radarr_form(self, client):
        resp = client.get("/setup")
        assert resp.status_code == 200
        assert b"radarr" in resp.content.lower()


class TestOverviewPage:
    def test_unconfigured_redirects_to_setup(self, client):
        resp = client.get("/overview", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)

    def test_configured_empty_data_returns_200(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/overview")
        assert resp.status_code == 200

    def test_with_weekly_json_renders_movie(self, client, weekly_json, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/overview")
        assert resp.status_code == 200
        assert b"Inception" in resp.content

    def test_status_filter_downloaded(self, client, weekly_json, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/overview?status=downloaded")
        assert resp.status_code == 200

    def test_status_filter_missing(self, client, weekly_json, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/overview?status=missing")
        assert resp.status_code == 200

    def test_status_filter_not_in_radarr(self, client, weekly_json, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/overview?status=not_in_radarr")
        assert resp.status_code == 200

    def test_status_filter_ignored(self, client, weekly_json, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/overview?status=ignored")
        assert resp.status_code == 200

    def test_search_filter(self, client, weekly_json, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/overview?search=inception")
        assert resp.status_code == 200
        assert b"Inception" in resp.content

    def test_year_filter(self, client, weekly_json, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/overview?year=2010")
        assert resp.status_code == 200

    def test_pagination(self, client, weekly_json, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/overview?page=1&per_page=20")
        assert resp.status_code == 200


class TestDashboardPage:
    def test_unconfigured_redirects(self, client):
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)

    def test_configured_returns_200(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_weeks_alias_returns_200(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/weeks")
        assert resp.status_code == 200

    def test_with_weekly_data(self, client, weekly_json, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.get("/dashboard")
        assert resp.status_code == 200
