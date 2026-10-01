"""ADK Web UI and NestedAgentLoader entry point for the OKF Spanner Query Agent."""

from query_agent.orchestrator import app, query_agent

root_agent = query_agent

__all__ = ["app", "query_agent", "root_agent"]
