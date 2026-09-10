# 0001 — Procesar el update dentro del request del webhook

**Fecha:** 2026-09-10 · **Estado:** aceptada

## Contexto
Telegram reintenta un update si no recibe 2xx en pocos segundos. La práctica habitual es responder
200 enseguida y procesar en segundo plano. Pero Cloud Run con `min-instances=0` y CPU asignada solo
durante el request (el modo gratuito) puede congelar la instancia apenas responde, dejando la
extracción a medias. Alternativas: (a) procesar síncrono dentro del request; (b) "CPU always
allocated", que cuesta dinero; (c) encolar en Cloud Tasks/Pub/Sub, más piezas para dos usuarios.

## Decisión
(a): el handler procesa el update completo (LLM → Pendientes → tarjeta) antes de responder 200.
Timeout de Cloud Run en 120 s (R15). Se responde 200 incluso ante errores internos para que
Telegram no reintente en loop; el error se loguea con `update_id` y el usuario recibe un mensaje
claro (R16). La deduplicación por `update_id` (R18) cubre el caso en que Telegram reintente igual.

## Consecuencias
Más simple y gratis. La latencia foto → tarjeta es la del LLM más Sheets, dentro del objetivo de
p95 < 10 s. Si algún día el procesamiento supera los ~30 s habría que pasar a (c).
