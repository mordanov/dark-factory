from mcp.server.fastmcp import FastMCP

from src.tools import document_store, git_read  # noqa: F401 — registers tools via decorators

mcp = FastMCP("agent-tools")

if __name__ == "__main__":
    mcp.run()
