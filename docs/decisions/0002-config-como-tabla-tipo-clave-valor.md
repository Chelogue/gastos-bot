# 0002 — `Config` como tabla tipo / clave / valor

**Fecha:** 2026-09-10 · **Estado:** aceptada

## Contexto
El PRD §9 dice qué guarda `Config` (IDs de Telegram, ingresos con `vigente_desde`, TC con fecha,
zona horaria, hora del reporte, porcentajes, IDs de carpetas de Drive) pero no cómo. Opciones:
(a) celdas fijas con nombre ("B3 es el TC"), frágil ante cualquier edición a mano; (b) varias
tablas chicas en una misma pestaña, difícil de leer por API; (c) una sola tabla larga.

## Decisión
(c): columnas `tipo | clave | valor | moneda | vigente_desde | nota`. Tipos: `persona`
(clave nombre, valor telegram_id), `ingreso` (clave nombre, valor monto, moneda, vigente_desde),
`tc` (clave `YYYY-MM`, valor UYU por USD, vigente_desde fecha de fijación), `param`
(zona_horaria, hora_reporte, pct_*), `carpeta` (clave ruta relativa en Drive, valor folder id).
El bot lee la pestaña entera en una llamada y la cachea 5 min, igual que `Categorias`.

## Consecuencias
Agregar un dato es agregar una fila, sin tocar el script. El TC queda con historial por mes
(D8, R7) y los ingresos con vigencia. Editar a mano es seguro: el bot busca por (tipo, clave),
no por posición. Si alguna vez hay más de dos personas (P2), son filas más.
