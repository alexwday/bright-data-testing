"""OpenAI function-calling tool schemas for Bright Data tools."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": (
                "Search Google via Bright Data SERP API. Returns organic results "
                "with title, url, and snippet. Use for finding web pages, documents, "
                "download links, company information, or any web query."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The Google search query string.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_page",
            "description": (
                "Scrape a web page via Bright Data Web Unlocker. Returns the page "
                "content converted to clean markdown format. Use this to read any "
                "web page, find links, extract information, or navigate sites. "
                "The content is automatically cleaned — HTML tags, scripts, and "
                "navigation elements are removed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the page to scrape.",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "download_file",
            "description": (
                "Download a file (PDF, XLSX, CSV, etc.) through Bright Data proxy "
                "and save it to disk. Returns file metadata including size, content "
                "type, and the original filename from the URL. After downloading, "
                "verify: (1) file size is reasonable (PDFs >20KB, XLSX >5KB), "
                "(2) content_type matches expected format, (3) url_filename is "
                "consistent with your intended document."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Direct download URL for the file.",
                    },
                    "filename": {
                        "type": "string",
                        "description": (
                            "Local filename to save as. Use the original "
                            "filename from the URL whenever possible — do not "
                            "invent or rename files."
                        ),
                    },
                },
                "required": ["url", "filename"],
            },
        },
    },
]
