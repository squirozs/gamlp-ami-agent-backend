"""Tests de integracion del endpoint de tramites, usando e-SITRAM en modo mock."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db.models.ciudadano import Ciudadano


@pytest.mark.asyncio
async def test_crear_y_obtener_tramite(client: AsyncClient, ciudadano_demo: Ciudadano) -> None:
    payload = {
        "ciudadano_id": str(ciudadano_demo.id),
        "tipo_tramite": "licencia_funcionamiento",
        "sistema_origen": "esitram",
        "metadata_tramite": {},
    }

    creado = await client.post("/api/v1/tramites", json=payload)
    assert creado.status_code == 201
    tramite_id = creado.json()["id"]
    assert creado.json()["estado"] == "iniciado"
    assert creado.json()["codigo_externo"].startswith("ESITRAM-MOCK-")

    obtenido = await client.get(f"/api/v1/tramites/{tramite_id}")
    assert obtenido.status_code == 200
    assert obtenido.json()["id"] == tramite_id


@pytest.mark.asyncio
async def test_obtener_tramite_inexistente_devuelve_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/tramites/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error_code"] == "not_found"


@pytest.mark.asyncio
async def test_crear_tramite_con_payload_invalido_devuelve_422(client: AsyncClient) -> None:
    response = await client.post("/api/v1/tramites", json={"tipo_tramite": "x"})

    assert response.status_code == 422
