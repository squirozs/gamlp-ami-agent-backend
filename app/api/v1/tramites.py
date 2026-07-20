"""GET /api/v1/tramites/{tramite_id} y endpoints relacionados."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import rate_limiter
from app.db.session import get_db_session
from app.integrations.factory import get_esitram_client
from app.models.tramite import TramiteCreateRequest, TramiteResponse
from app.services.tramite_service import TramiteService

router = APIRouter(prefix="/tramites", tags=["tramites"])


@router.get(
    "/{tramite_id}",
    response_model=TramiteResponse,
    dependencies=[Depends(rate_limiter(scope="tramites_get", limit_per_minute=30))],
)
async def obtener_tramite(
    tramite_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db_session)]
) -> TramiteResponse:
    service = TramiteService(session, get_esitram_client())
    tramite = await service.obtener(tramite_id)
    return TramiteResponse.model_validate(tramite)


@router.get(
    "",
    response_model=list[TramiteResponse],
    dependencies=[Depends(rate_limiter(scope="tramites_list", limit_per_minute=30))],
)
async def listar_tramites_por_ciudadano(
    ciudadano_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db_session)]
) -> list[TramiteResponse]:
    service = TramiteService(session, get_esitram_client())
    tramites = await service.listar_por_ciudadano(ciudadano_id)
    return [TramiteResponse.model_validate(t) for t in tramites]


@router.post(
    "",
    response_model=TramiteResponse,
    status_code=201,
    dependencies=[Depends(rate_limiter(scope="tramites_create", limit_per_minute=10))],
)
async def crear_tramite(
    payload: TramiteCreateRequest, session: Annotated[AsyncSession, Depends(get_db_session)]
) -> TramiteResponse:
    service = TramiteService(session, get_esitram_client())
    tramite = await service.crear(
        ciudadano_id=payload.ciudadano_id,
        tipo_tramite=payload.tipo_tramite,
        sistema_origen=payload.sistema_origen,
        metadata_tramite=payload.metadata_tramite,
    )
    return TramiteResponse.model_validate(tramite)
