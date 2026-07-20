"""Logica de negocio para validacion de documentos por vision.

La imagen se recibe como bytes en memoria, se envia al modelo multimodal y se
descarta inmediatamente despues de obtener el resultado: nunca se escribe a disco
ni se indexa en el vector store (ver docs/decisiones-tecnicas.md)."""

from __future__ import annotations

import base64
import uuid
from typing import Any

from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.core.exceptions import DocumentValidationError
from app.db.models.documento_validado import DocumentoValidado, ResultadoValidacion
from app.db.session import AsyncSessionLocal

_PROMPT_VALIDACION = """Eres un asistente que valida fotos de documentos oficiales bolivianos \
para tramites municipales del GAMLP. Analiza la imagen adjunta de un documento de tipo \
"{tipo_documento}" y responde EXCLUSIVAMENTE en este formato JSON, sin texto adicional:

{{"resultado": "aprobado" | "observado" | "rechazado", \
"observaciones": {{"legible": true|false, "completo": true|false, "detalle": "texto breve"}}}}

Criterios: "aprobado" si el documento es legible, completo y corresponde al tipo esperado. \
"observado" si hay problemas menores (foto borrosa, corte de bordes) que probablemente \
requieran repetir la foto. "rechazado" si el documento no corresponde al tipo esperado o \
esta vencido/ilegible."""


class DocumentoService:
    """Valida documentos via el modelo multimodal de Anthropic, sin persistir la imagen."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = settings.ANTHROPIC_MODEL

    async def validar(
        self,
        tramite_id: uuid.UUID,
        tipo_documento: str,
        imagen_bytes: bytes,
        media_type: str,
    ) -> DocumentoValidado:
        resultado_dict = await self._analizar_con_vision(tipo_documento, imagen_bytes, media_type)
        # imagen_bytes queda fuera de alcance aqui; no se guarda en ninguna variable persistente.

        documento = DocumentoValidado(
            tramite_id=tramite_id,
            tipo_documento=tipo_documento,
            resultado=ResultadoValidacion(resultado_dict["resultado"]),
            observaciones=resultado_dict["observaciones"],
        )
        async with AsyncSessionLocal() as session:
            session.add(documento)
            await session.commit()
            await session.refresh(documento)
        return documento

    async def _analizar_con_vision(
        self, tipo_documento: str, imagen_bytes: bytes, media_type: str
    ) -> dict[str, Any]:
        import json

        imagen_b64 = base64.b64encode(imagen_bytes).decode("utf-8")
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {  # type: ignore[list-item]
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": imagen_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": _PROMPT_VALIDACION.format(tipo_documento=tipo_documento),
                            },
                        ],
                    }
                ],
            )
            texto = response.content[0].text if response.content else "{}"  # type: ignore[union-attr]
            data: dict[str, Any] = json.loads(texto)
            return data
        except (
            Exception
        ) as exc:  # noqa: BLE001 - cualquier fallo de vision se traduce a error de dominio
            raise DocumentValidationError(
                "No se pudo analizar el documento. Intenta con otra foto mas clara."
            ) from exc
