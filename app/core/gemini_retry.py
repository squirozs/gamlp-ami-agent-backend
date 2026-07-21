"""Reintento acotado para llamadas a la API de Gemini.

El nivel gratuito de AI Studio devuelve intermitentemente `503 UNAVAILABLE` ("high
demand") o `429 RESOURCE_EXHAUSTED` de forma transitoria (verificado en vivo durante
el desarrollo: la misma request fallaba y funcionaba segundos despues sin cambiar
nada). Un reintento corto con backoff evita que eso tumbe una demo en vivo, sin caer
en reintentos infinitos (mismo criterio que el circuit breaker de integraciones
municipales, ver ADR-005 en docs/decisiones-tecnicas.md)."""

from __future__ import annotations

from google.genai import errors as genai_errors
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _es_error_transitorio(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return exc.code == 429
    return False


gemini_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_es_error_transitorio),
)
