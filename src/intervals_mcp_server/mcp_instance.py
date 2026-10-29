"""
Shared MCP instance module.

This module provides a shared FastMCP instance that can be imported by both
the server module and tool modules without creating cyclic imports.
"""

import logging
import os

from fastmcp import FastMCP

from intervals_mcp_server.api.client import setup_api_client
from intervals_mcp_server.write_policy import current_policy, is_tool_allowed

logger = logging.getLogger("intervals_icu_mcp_server")

_mcp_client_id = os.getenv("MCP_CLIENT_ID", "")
_mcp_client_secret = os.getenv("MCP_CLIENT_SECRET", "")
_mcp_server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8000")

_auth_server_provider = None

if _mcp_client_id and _mcp_client_secret:
    from intervals_mcp_server.auth import SingleClientOAuthProvider

    # This server is both the authorization server and the resource server, so
    # base_url/issuer_url/resource_base_url all point at the same public HTTPS
    # URL: base_url/issuer_url publish /.well-known/oauth-authorization-server
    # (AS metadata) and resource_base_url publishes
    # /.well-known/oauth-protected-resource (RFC 9728), which Claude.ai's
    # connector flow requires to authorize.
    _auth_server_provider = SingleClientOAuthProvider(
        _mcp_client_id,
        _mcp_client_secret,
        base_url=_mcp_server_url,
    )
    logger.info("OAuth authentication enabled for HTTP transport.")
else:
    logger.debug("MCP_CLIENT_ID/MCP_CLIENT_SECRET not set; HTTP endpoint is unauthenticated.")

mcp: FastMCP = FastMCP(
    "intervals-icu",
    lifespan=setup_api_client,
    auth=_auth_server_provider,
)


# --- Write policy: tool layer -------------------------------------------------
# Tools register themselves with ``@mcp.tool(...)`` at import time. Wrap the
# decorator so write tools blocked by the policy are never registered: the
# function stays importable (tests, re-exports) but MCP clients cannot see it.
_register_tool = mcp.tool


def _policy_tool(*args, **kwargs):  # type: ignore[no-untyped-def]
    def _apply(fn, decorator):  # type: ignore[no-untyped-def]
        if not is_tool_allowed(fn.__name__):
            logger.info("Tool %s not registered (write policy %s)", fn.__name__, current_policy())
            return fn
        return decorator(fn)

    # Bare usage: @mcp.tool
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return _apply(args[0], _register_tool)

    decorator = _register_tool(*args, **kwargs)
    return lambda fn: _apply(fn, decorator)


mcp.tool = _policy_tool  # type: ignore[method-assign]
logger.info("Write policy: %s", current_policy())
