"""Tool registry: mapea nombre de tool -> definicion (schema + handler async).

Usar un registro en vez de un if/elif gigante en el orquestador permite que el
numero de tools crezca (nuevos tipos de tramite, nuevas integraciones) sin
reescribir el loop del agente."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    """Registro central de tools disponibles para el agente orquestador."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self, name: str, description: str, input_schema: dict[str, Any]
    ) -> Callable[[ToolHandler], ToolHandler]:
        def decorator(handler: ToolHandler) -> ToolHandler:
            self._tools[name] = ToolDefinition(
                name=name, description=description, input_schema=input_schema, handler=handler
            )
            return handler

        return decorator

    def anthropic_tool_specs(self) -> list[dict[str, Any]]:
        """Formato esperado por el parametro `tools` del SDK de Anthropic."""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools.values()
        ]

    async def ejecutar(self, name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            return {"error": f"Tool desconocida: {name}"}
        return await self._tools[name].handler(tool_input)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


tool_registry = ToolRegistry()
