"""
Write policy for the Intervals.icu MCP server.

This fork restricts what the server is allowed to change on Intervals.icu.
By default (policy ``plans_workouts``) the server is read-only, except for:

* training plans (``get``/``change_training_plan``, ``apply_plan_changes``,
  ``apply_plan_to_calendar``, ``change_athlete_plans_bulk``);
* the workout library (``create_workout``, ``update_workout``,
  ``schedule_workout``);
* calendar events (``add_or_update_event``, ``delete_event``,
  ``delete_events_by_date_range``).

Two independent layers enforce it:

1. **Tool layer** — write tools outside the allowlist are never registered
   with the MCP server, so clients cannot even see them.
2. **HTTP layer** — ``make_intervals_request`` refuses any non-GET request
   whose method + path is not on ``ALLOWED_WRITE_ENDPOINTS``. ``DELETE`` is
   only accepted on a single calendar event.

Set ``INTERVALS_WRITE_POLICY=full`` to restore the upstream behaviour (all
tools, all methods). Any other value, or no value, means ``plans_workouts``.
"""

from __future__ import annotations

import os
import re

POLICY_FULL = "full"
POLICY_PLANS_WORKOUTS = "plans_workouts"

# Write tools that are NOT exposed under the restricted policy.
BLOCKED_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        # activities
        "add_activity_message",
        "update_activity",
        "delete_activity",
        "create_manual_activity",
        "bulk_create_manual_activities",
        # activity intervals
        "update_activity_intervals",
        "update_activity_interval",
        "delete_activity_intervals",
        "split_activity_interval",
        # custom items
        "create_custom_item",
        "update_custom_item",
        "delete_custom_item",
    }
)

# Write tools that stay available under the restricted policy.
ALLOWED_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "change_training_plan",
        "apply_plan_changes",
        "apply_plan_to_calendar",
        "change_athlete_plans_bulk",
        "create_workout",
        "update_workout",
        "schedule_workout",
        # calendar events
        "add_or_update_event",
        "delete_event",
        "delete_events_by_date_range",
    }
)

_ATHLETE = r"/athlete/[^/]+"

# (method, path regex) pairs the HTTP layer accepts besides GET.
ALLOWED_WRITE_ENDPOINTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # training plans
    ("PUT", re.compile(rf"^{_ATHLETE}/training-plan/?$")),
    ("PUT", re.compile(rf"^{_ATHLETE}/apply-plan-changes/?$")),
    ("POST", re.compile(rf"^{_ATHLETE}/events/apply-plan/?$")),
    ("PUT", re.compile(r"^/athlete-plans/?$")),
    # workout library
    ("POST", re.compile(rf"^{_ATHLETE}/workouts/?$")),
    ("PUT", re.compile(rf"^{_ATHLETE}/workouts/[^/]+/?$")),
    # schedule_workout: puts a library workout on the calendar
    ("POST", re.compile(rf"^{_ATHLETE}/events/?$")),
    # calendar events: update / delete one event (delete_events_by_date_range
    # deletes event by event through the same endpoint)
    ("PUT", re.compile(rf"^{_ATHLETE}/events/[^/]+/?$")),
    ("DELETE", re.compile(rf"^{_ATHLETE}/events/[^/]+/?$")),
)


def current_policy() -> str:
    """Return the active write policy (read from the environment each call)."""
    value = os.getenv("INTERVALS_WRITE_POLICY", POLICY_PLANS_WORKOUTS).strip().lower()
    return POLICY_FULL if value == POLICY_FULL else POLICY_PLANS_WORKOUTS


def is_tool_allowed(name: str) -> bool:
    """Whether a tool may be registered under the active policy."""
    if current_policy() == POLICY_FULL:
        return True
    return name not in BLOCKED_WRITE_TOOLS


def _path_only(url: str) -> str:
    """Strip scheme, host, API prefix and query string from a request URL."""
    path = re.sub(r"^https?://[^/]+", "", url)
    path = path.split("?", 1)[0]
    return re.sub(r"^/api/v1(?=/)", "", path)


def is_request_allowed(method: str, url: str) -> bool:
    """Whether an HTTP request to Intervals.icu is allowed under the active policy."""
    verb = method.upper()
    if verb in {"GET", "HEAD", "OPTIONS"} or current_policy() == POLICY_FULL:
        return True
    path = _path_only(url)
    return any(verb == m and pattern.match(path) for m, pattern in ALLOWED_WRITE_ENDPOINTS)
