"""Logica de negocio para conversaciones y mensajes (historial del agente por ciudadano)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.ciudadano import Ciudadano
from app.db.models.conversacion import Conversacion, Mensaje, RolMensaje


class ConversacionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obtener_o_crear_ciudadano(self, telefono_whatsapp: str) -> Ciudadano:
        result = await self._session.execute(
            select(Ciudadano).where(Ciudadano.telefono_whatsapp == telefono_whatsapp)
        )
        ciudadano = result.scalar_one_or_none()
        if ciudadano is None:
            ciudadano = Ciudadano(telefono_whatsapp=telefono_whatsapp)
            self._session.add(ciudadano)
            await self._session.commit()
            await self._session.refresh(ciudadano)
        return ciudadano

    async def obtener_conversacion_activa(self, ciudadano_id: uuid.UUID) -> Conversacion:
        result = await self._session.execute(
            select(Conversacion)
            .where(Conversacion.ciudadano_id == ciudadano_id, Conversacion.activa.is_(True))
            .options(selectinload(Conversacion.mensajes))
        )
        conversacion = result.scalar_one_or_none()
        if conversacion is None:
            conversacion = Conversacion(ciudadano_id=ciudadano_id, activa=True)
            self._session.add(conversacion)
            await self._session.commit()
            await self._session.refresh(conversacion)
        return conversacion

    async def agregar_mensaje(
        self, conversacion_id: uuid.UUID, rol: RolMensaje, contenido: str
    ) -> Mensaje:
        mensaje = Mensaje(conversacion_id=conversacion_id, rol=rol, contenido=contenido)
        self._session.add(mensaje)
        await self._session.commit()
        await self._session.refresh(mensaje)
        return mensaje

    async def historial(self, conversacion_id: uuid.UUID, limite: int = 20) -> list[Mensaje]:
        result = await self._session.execute(
            select(Mensaje)
            .where(Mensaje.conversacion_id == conversacion_id)
            .order_by(Mensaje.created_at.desc())
            .limit(limite)
        )
        mensajes = list(result.scalars().all())
        mensajes.reverse()
        return mensajes
