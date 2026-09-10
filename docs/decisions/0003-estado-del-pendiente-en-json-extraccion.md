# 0003 — Estado del pendiente dentro de `json_extraccion`; dedupe por la pestaña Pendientes

**Fecha:** 2026-09-10 · **Estado:** aceptada

## Contexto
La tarjeta tiene dos pasos y ediciones (R3). Con webhook sin estado y `min-instances=0`, todo lo
que pasa entre toques tiene que vivir en el Sheet: la elección compartido/personal, los campos
corregidos, qué respuesta de texto (ForceReply) se espera y el `message_id` de la tarjeta para
editarla. El PRD §9 fija las columnas de `Pendientes` y no las incluye. Además D4 pide deduplicar
`update_id` sin base de datos.

## Decisión
La columna `json_extraccion` guarda el modelo `Pendiente` completo (extracción + `compartido`,
`ediciones`, `esperando`, `mensaje_tarjeta_id`, `estado`, `gasto_id`), no solo lo que dijo el LLM.
Las demás columnas (`pendiente_id`, `update_id`, `telegram_id`, `file_id`, `creado`, `expira`)
quedan como índices legibles. Las filas no se borran al guardar o descartar: cambian de `estado`
y se purgan cuando pasa `expira` (48 h, D5). Así la misma pestaña sirve para deduplicar
`update_id` durante esa ventana (D4 pedía 24 h; 48 h la cubre). El `callback_data` de los botones
lleva solo `<accion>:<pendiente_id>[:<valor>]`.

## Consecuencias
Sin cambios al esquema del Sheet. Cada toque cuesta una lectura de la pestaña Pendientes (chica:
decenas de filas como mucho). Si algún día se quiere un historial de pendientes, es cuestión de
no purgar. Si el JSON se edita a mano y rompe, el pendiente se ignora y el usuario reenvía la foto.
