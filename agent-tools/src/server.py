from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agent-tools")

from src.tools import git_read, document_store  # noqa: F401 — registers tools via decorators

if __name__ == "__main__":
    mcp.run()
