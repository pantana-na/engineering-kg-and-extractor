"""ADK Web UI and NestedAgentLoader entry point."""

from extracter_agent.agent.orchestrator import app, extracter_agent

root_agent = extracter_agent

__all__ = ["app", "extracter_agent", "root_agent"]
