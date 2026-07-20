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


def test_anthropic_tool_specs_incluye_nombre_y_schema() -> None:
    registry = ToolRegistry()

    @registry.register(
        name="ping", description="ping", input_schema={"type": "object", "properties": {}}
    )
    async def ping(tool_input: dict[str, object]) -> dict[str, object]:
        return {}

    specs = registry.anthropic_tool_specs()

    assert specs == [
        {
            "name": "ping",
            "description": "ping",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]
