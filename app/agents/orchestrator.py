"""Orquestador del agente: recibe un mensaje del ciudadano, corre el loop de tool use
de Anthropic y devuelve la respuesta final de texto.

No contiene logica de negocio de dominio: cada capacidad concreta vive en una tool
independiente y testeable (app/agents/tools/). El orquestador solo sabe conversar con
el modelo y despachar llamadas a traves del tool_registry."""

from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

from app.agents.prompts import SYSTEM_PROMPT
from app.agents.tools import tool_registry
from app.agents.tools.validate_document import imagen_actual
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_TOOL_ITERATIONS = 6


class TramiteOrchestrator:
    """Ejecuta el loop de agente (mensaje -> tool use -> respuesta) para una conversacion."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = settings.ANTHROPIC_MODEL
        self._max_tokens = settings.ANTHROPIC_MAX_TOKENS

    async def responder(
        self,
        historial: list[MessageParam],
        mensaje_ciudadano: str,
        imagen: tuple[bytes, str] | None = None,
    ) -> str:
        """Procesa un turno de conversacion y devuelve el texto de respuesta del agente.

        `imagen` (bytes, media_type) se deja disponible solo para la tool
        validar_documento durante este turno; nunca se persiste."""
        token = imagen_actual.set(imagen) if imagen is not None else None
        try:
            messages: list[MessageParam] = [
                *historial,
                {"role": "user", "content": mensaje_ciudadano},
            ]

            for _ in range(_MAX_TOOL_ITERATIONS):
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=SYSTEM_PROMPT,
                    tools=tool_registry.anthropic_tool_specs(),  # type: ignore[arg-type]
                    messages=messages,
                )

                if response.stop_reason != "tool_use":
                    return _extraer_texto(response.content)

                messages.append({"role": "assistant", "content": response.content})
                tool_results: list[dict[str, Any]] = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    logger.info("agent_tool_call", tool_name=block.name)
                    resultado = await tool_registry.ejecutar(block.name, dict(block.input))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": _to_text(resultado),
                        }
                    )

                messages.append({"role": "user", "content": tool_results})  # type: ignore[typeddict-item]

            return (
                "Estoy teniendo dificultades para completar esta consulta. "
                "Por favor intenta reformularla o contacta a una oficina del GAMLP."
            )
        finally:
            if token is not None:
                imagen_actual.reset(token)


def _extraer_texto(content: Any) -> str:
    partes = [block.text for block in content if getattr(block, "type", None) == "text"]
    return "\n".join(partes).strip() or "No tengo una respuesta para eso en este momento."


def _to_text(resultado: dict[str, Any]) -> str:
    import json

    return json.dumps(resultado, ensure_ascii=False)
