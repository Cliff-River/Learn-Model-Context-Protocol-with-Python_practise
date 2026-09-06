# %% package
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.models import InitializationOptions
from mcp.server.sse import SseServerTransport

import tools

# %%

server = Server("low-level server")

def pydamtic_to_json(model_cls : type) -> dict:
    schema = model_cls.schema()
    properties = {}
    required = schema.get("required", [])
    for proq, detail in schema.get("properties", {}).items():
        properties[proq] = { "type": detail.get("type", "string") }
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }

