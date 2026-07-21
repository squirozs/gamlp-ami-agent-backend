"""POST /api/v1/webhooks/whatsapp - recibe mensajes entrantes de WhatsApp via Twilio.

Verifica X-Twilio-Signature ANTES de procesar cualquier payload (requisito de
seguridad no negociable). Sin firma valida, responde 401 y no toca la base de datos
ni invoca al agente."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, Request

from app.agents.orchestrator import TramiteOrchestrator
from app.api.v1.deps import rate_limiter
from app.core.config import get_settings
from app.core.exceptions import InvalidWebhookSignatureError, MunicipalAPIUnavailableError
from app.core.logging import get_logger
from app.core.security import verify_twilio_signature
from app.db.models.conversacion import RolMensaje
from app.db.session import AsyncSessionLocal
from app.integrations.whatsapp_client import WhatsAppClient
from app.models.common import ApiModel
from app.services.conversacion_service import ConversacionService

router = APIRouter(tags=["webhooks"])
logger = get_logger(__name__)


class WebhookAck(ApiModel):
    recibido: bool


@router.post(
    "/webhooks/whatsapp",
    response_model=WebhookAck,
    summary="Webhook entrante de WhatsApp (Twilio)",
    dependencies=[Depends(rate_limiter(scope="webhook_whatsapp", limit_per_minute=60))],
)
async def whatsapp_webhook(
    request: Request,
    x_twilio_signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> WebhookAck:
    settings = get_settings()
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}

    if settings.TWILIO_WEBHOOK_VALIDATE:
        if not x_twilio_signature:
            raise InvalidWebhookSignatureError("Falta X-Twilio-Signature")
        url = str(request.url)
        verify_twilio_signature(settings.TWILIO_AUTH_TOKEN, url, params, x_twilio_signature)

    telefono = params.get("From", "")
    cuerpo = params.get("Body", "")
    num_media = int(params.get("NumMedia", "0") or "0")

    imagen: tuple[bytes, str] | None = None
    if num_media > 0:
        media_url = params.get("MediaUrl0")
        media_type = params.get("MediaContentType0", "image/jpeg")
        if media_url:
            imagen = await _descargar_media(
                media_url, settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, media_type
            )

    async with AsyncSessionLocal() as session:
        conv_service = ConversacionService(session)
        ciudadano = await conv_service.obtener_o_crear_ciudadano(telefono)
        conversacion = await conv_service.obtener_conversacion_activa(ciudadano.id)

        await conv_service.agregar_mensaje(conversacion.id, RolMensaje.CIUDADANO, cuerpo)

        historial_mensajes = await conv_service.historial(conversacion.id, limite=20)
        # Gemini usa los roles "user"/"model" (no "assistant" como Anthropic/OpenAI).
        historial_gemini: list[dict[str, str]] = [
            {
                "role": "user" if m.rol == RolMensaje.CIUDADANO else "model",
                "content": m.contenido,
            }
            for m in historial_mensajes[:-1]
        ]

        orchestrator = TramiteOrchestrator()
        respuesta = await orchestrator.responder(historial_gemini, cuerpo, imagen=imagen)

        await conv_service.agregar_mensaje(conversacion.id, RolMensaje.AGENTE, respuesta)

    # El mensaje del ciudadano y la respuesta del agente ya quedaron persistidos
    # arriba aunque el envio saliente falle: no queremos reprocesar todo el turno
    # (y potencialmente duplicar la respuesta) si Twilio reintenta este webhook
    # solo porque el envio de salida tuvo un problema transitorio.
    try:
        whatsapp = WhatsAppClient()
        await whatsapp.enviar_mensaje(telefono, respuesta)
    except MunicipalAPIUnavailableError:
        logger.warning("whatsapp_reply_send_failed", num_media=num_media)

    logger.info("whatsapp_webhook_procesado", num_media=num_media)
    return WebhookAck(recibido=True)


async def _descargar_media(
    media_url: str, account_sid: str, auth_token: str, media_type: str
) -> tuple[bytes, str] | None:
    """Descarga la imagen adjunta de Twilio en memoria (no se escribe a disco)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(media_url, auth=(account_sid, auth_token))
            response.raise_for_status()
            return response.content, media_type
    except httpx.HTTPError:
        logger.warning("whatsapp_media_download_failed")
        return None
