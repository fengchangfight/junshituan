"""Web search tool using DuckDuckGo (free, no API key)."""

from __future__ import annotations

from app.tools import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web for current information. "
        "Use when you need facts beyond your knowledge cutoff, recent news, "
        "or up-to-date documentation. Returns titles, URLs, and snippets."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string. Be specific — use terms likely to appear in target pages.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5, max 10).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    @property
    def prompt_snippet(self) -> str:
        return (
            "## Web Search Tool\n"
            "You have access to a `web_search` tool that performs live web searches.\n"
            "- Use it when the user asks about recent events, current data, or facts you're unsure about.\n"
            "- Provide a specific, keyword-rich query. Avoid vague questions.\n"
            "- After receiving results, cite sources as markdown links: `[Title](URL)`.\n"
            "- Only use this tool when necessary — don't search for things you already know confidently.\n"
            "- **Important: limit to 1-2 searches total. Batch your queries efficiently.**\n"
            "  After getting search results, respond directly — do NOT search again."
        )

    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        """Perform a DuckDuckGo text search."""
        max_results = min(max(1, max_results), 10)
        print(f"[DEBUG web_search] START query='{query}' max_results={max_results}", flush=True)

        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                print(f"[DEBUG web_search] neither ddgs nor duckduckgo_search installed", flush=True)
                return ToolResult(
                    content="Error: search library not installed. "
                    "Install it with: pip install ddgs"
                )

        print(f"[DEBUG web_search] query='{query}' max_results={max_results}", flush=True)
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
        except Exception as exc:
            print(f"[DEBUG web_search] ERROR: {type(exc).__name__}: {exc}", flush=True)
            return ToolResult(content=f"Web search failed: {exc}")

        print(f"[DEBUG web_search] got {len(results)} results", flush=True)

        if not results:
            return ToolResult(content=f"No results found for query: '{query}'")

        lines = [f"Search results for: '{query}'\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            href = r.get("href", "")
            body = r.get("body", "")
            # Truncate body to keep context lean
            snippet = body[:300] + "..." if len(body) > 300 else body
            lines.append(f"{i}. **{title}**\n   {snippet}\n   {href}\n")

        return ToolResult(
            content="\n".join(lines),
            data={"query": query, "results": results},
        )


web_search_tool = WebSearchTool()
