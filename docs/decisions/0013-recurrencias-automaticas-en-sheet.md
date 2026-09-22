# 0013 — Recurrencias automáticas en una pestaña propia

**Fecha:** 2026-09-22 · **Estado:** aceptada

## Contexto
ADR 0009 resolvió alquileres y suscripciones con `/repetir <ID>`, pero seguía exigiendo una acción
manual en cada período. El producto ahora necesita declarar una vez la periodicidad y registrar
las ocurrencias automáticamente, sin incorporar memoria conversacional ni otra base de datos.

## Decisión
Después de guardar un gasto, Telegram pregunta si es único o recurrente. Una recurrencia puede ser
mensual, trimestral, semestral o anual y conserva el día del gasto original; si el mes no tiene ese
día, usa el último disponible. Las plantillas viven en la pestaña visible `Recurrentes`. Un job
diario materializa las vencidas, vincula cada movimiento con `recurrente_id` y avisa solamente a
quien creó la plantilla. El aviso permite confirmar que sigue igual, modificar solo la ocurrencia,
modificarla junto con las futuras o finalizarla. Sin respuesta, continúa activa.

## Consecuencias
El job es idempotente por recurrencia y fecha, usa el tipo de cambio del mes y recalcula el
Dashboard. Los gastos históricos no cambian al editar o finalizar una plantilla. Se agrega un
tercer job de Cloud Scheduler y una migración aditiva del Sheet. `/repetir` se conserva como atajo
manual y ADR 0009 sigue vigente solo para ese comando.
