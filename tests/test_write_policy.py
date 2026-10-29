"""Tests for the fork's write policy (tool layer + HTTP layer)."""

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("API_KEY", "test")
os.environ.setdefault("ATHLETE_ID", "i1")

import pytest  # noqa: E402

import intervals_mcp_server.server  # noqa: E402, F401  (registers all tools)
from intervals_mcp_server.api.client import make_intervals_request  # noqa: E402
from intervals_mcp_server.mcp_instance import mcp  # noqa: E402
from intervals_mcp_server.write_policy import (  # noqa: E402
    ALLOWED_WRITE_TOOLS,
    BLOCKED_WRITE_TOOLS,
    is_request_allowed,
)


def _registered() -> set[str]:
    return {tool.name for tool in asyncio.run(mcp.list_tools())}


def test_blocked_write_tools_are_not_registered():
    assert not _registered() & BLOCKED_WRITE_TOOLS


def test_plan_and_workout_write_tools_are_registered():
    assert ALLOWED_WRITE_TOOLS <= _registered()


def test_every_registered_write_tool_is_allowlisted():
    for tool in asyncio.run(mcp.list_tools()):
        if tool.name in ALLOWED_WRITE_TOOLS:
            continue
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True, f"{tool.name} can write"


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("GET", "/athlete/i1/activities"),
        ("GET", "/activity/123"),
        ("PUT", "/athlete/i1/training-plan"),
        ("PUT", "/athlete/i1/apply-plan-changes"),
        ("POST", "/athlete/i1/events/apply-plan"),
        ("PUT", "/athlete-plans"),
        ("POST", "/athlete/i1/workouts"),
        ("PUT", "/athlete/i1/workouts/42"),
        ("POST", "/athlete/i1/events"),
        ("POST", "https://intervals.icu/api/v1/athlete/i1/workouts?x=1"),
    ],
)
def test_allowed_requests(method, url):
    assert is_request_allowed(method, url)


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("DELETE", "/athlete/i1/events/9"),
        ("DELETE", "/activity/123"),
        ("DELETE", "/athlete/i1/workouts/42"),
        ("PUT", "/activity/123"),
        ("PUT", "/athlete/i1/events/9"),
        ("POST", "/activity/123/messages"),
        ("POST", "/athlete/i1/activities/manual"),
        ("PUT", "/activity/123/intervals"),
        ("POST", "/athlete/i1/custom-item"),
        ("PUT", "/athlete/i1/wellness/2026-10-29"),
        ("PUT", "/athlete/i1/sport-settings/1"),
        ("PUT", "/athlete/i1"),
        ("POST", "/athlete/i1/workouts/42/extra"),
    ],
)
def test_blocked_requests(method, url):
    assert not is_request_allowed(method, url)


def test_blocked_request_never_reaches_network(monkeypatch):
    def _boom(*_a, **_kw):
        raise AssertionError("network must not be called for a blocked request")

    monkeypatch.setattr("intervals_mcp_server.api.client._get_httpx_client", _boom)
    result = asyncio.run(make_intervals_request(url="/activity/123", method="DELETE"))
    assert isinstance(result, dict) and result["error"] is True
    assert "write policy" in result["message"]


def test_full_policy_restores_upstream_behaviour(monkeypatch):
    monkeypatch.setenv("INTERVALS_WRITE_POLICY", "full")
    assert is_request_allowed("DELETE", "/activity/123")
