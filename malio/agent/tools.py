"""Stage 4: Tool registry — register, schema, and execute."""
from typing import Any, Callable, Dict, List, Optional


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, dict] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, str],
        handler: Callable,
    ):
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler": handler,
        }

    def get_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": info["name"],
                "description": info["description"],
                "parameters": info["parameters"],
            }
            for info in self._tools.values()
        ]

    def execute(self, name: str, params: Dict[str, Any]) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Tool '{name}' not found"}
        try:
            result = tool["handler"](**params)
            return result if result is not None else {"result": None}
        except Exception as e:
            return {"error": f"Tool '{name}' execution failed: {e}"}

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": info["name"],
                "description": info["description"],
                "parameters": info["parameters"],
            }
            for info in self._tools.values()
        ]
