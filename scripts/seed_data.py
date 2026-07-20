"""Script de datos ficticios para demo: crea ciudadanos, tramites y una fuente
normativa de ejemplo. Uso: python -m scripts.seed_data"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

from app.core.logging import configure_logging, get_logger
from app.db.models.ciudadano import Ciudadano
from app.db.models.fuente_normativa import FuenteNormativa
from app.db.models.recordatorio import EstadoRecordatorio, Recordatorio
from app.db.models.tramite import EstadoTramite, Tramite
from app.db.session import AsyncSessionLocal

logger = get_logger(__name__)


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        ciudadano = Ciudadano(
            id=uuid.uuid4(), telefono_whatsapp="whatsapp:+59171234567", nombre="Maria Quispe"
        )
        session.add(ciudadano)
        await session.flush()

        tramite = Tramite(
            id=uuid.uuid4(),
            ciudadano_id=ciudadano.id,
            tipo_tramite="licencia_funcionamiento",
            sistema_origen="esitram",
            codigo_externo="ESITRAM-DEMO-0001",
            estado=EstadoTramite.EN_REVISION,
            metadata_tramite={"actividad_economica": "tienda de abarrotes"},
        )
        session.add(tramite)

        fuente = FuenteNormativa(
            id=uuid.uuid4(),
            titulo="Ordenanza Municipal 123/2024 - Licencias de Funcionamiento",
            numero_norma="OM 123/2024",
            fecha_vigencia=date(2024, 1, 15),
            url_fuente="https://lapaz.bo/normativa/om-123-2024",
            chroma_collection="normativa_municipal",
        )
        session.add(fuente)

        recordatorio = Recordatorio(
            id=uuid.uuid4(),
            ciudadano_id=ciudadano.id,
            tramite_id=tramite.id,
            idempotency_key=f"{ciudadano.id}:{tramite.id}:seed-demo",
            mensaje="Recuerda que tu licencia de funcionamiento vence en 5 dias.",
            fecha_programada=datetime.now(UTC) + timedelta(days=1),
            estado=EstadoRecordatorio.PENDIENTE,
        )
        session.add(recordatorio)

        await session.commit()
        logger.info("seed_data_creado", ciudadano_id=str(ciudadano.id), tramite_id=str(tramite.id))


if __name__ == "__main__":
    configure_logging()
    asyncio.run(seed())
