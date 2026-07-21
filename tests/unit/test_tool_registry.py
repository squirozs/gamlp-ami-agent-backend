"""Tests unitarios del registro de tools del agente."""

from __future__ import annotations

import pytest

from app.agents.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_registry_ejecuta_tool_registrada() -> None:
    registry = ToolRegistry()

    @registry.register(
        name="saludar", description="saluda", input_schema={"type": "object", "properties": {}}
    )
    async def saludar(tool_input: dict[str, object]) -> dict[str, object]:
        return {"mensaje": "hola"}

    resultado = await registry.ejecutar("saludar", {})

    assert resultado == {"mensaje": "hola"}
    assert "saludar" in registry


@pytest.mark.asyncio
async def test_registry_devuelve_error_para_tool_desconocida() -> None:
    registry = ToolRegistry()

    resultado = await registry.ejecutar("no_existe", {})

    assert "error" in resultado


def test_gemini_tools_incluye_nombre_y_schema_en_mayuscula() -> None:
    registry = ToolRegistry()

    @registry.register(
        name="ping",
        description="ping",
        input_schema={
            "type": "object",
            "properties": {"consulta": {"type": "string", "description": "texto"}},
        },
    )
    async def ping(tool_input: dict[str, object]) -> dict[str, object]:
        return {}

    tools = registry.gemini_tools()

    assert len(tools) == 1
    declarations = tools[0].function_declarations
    assert declarations is not None
    assert len(declarations) == 1
    declaration = declarations[0]
    assert declaration.name == "ping"
    assert declaration.description == "ping"
    assert declaration.parameters is not None
    assert declaration.parameters.type == "OBJECT"
    assert declaration.parameters.properties["consulta"].type == "STRING"
