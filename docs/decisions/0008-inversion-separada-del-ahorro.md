# 0008 — La inversión se muestra aparte del ahorro (y apartar no es gastar)

**Fecha:** 2026-09-11 · **Estado:** aceptada (pedido de Marcelo; no cambia el 50/30/20 del PRD)

## Contexto
El rubro `Ahorro` del PRD §10 junta tres subcategorías: Ahorro, Inversión y Pago extra de deuda.
En el Dashboard eso era una sola columna (`ahorro_declarado_usd`) y en el reporte una sola línea,
así que invertir 500 y guardar 500 se veían igual. Marcelo pidió poder distinguirlos. Además, en
el reporte la inversión aparecía mezclada con el supermercado en "en qué se fue la plata", que es
justo lo contrario de lo que pasó: esa plata no se fue.

## Decisión
Los rubros del PRD no se tocan: la inversión sigue contando dentro del 20 %. Cambia cómo se
muestra. En el Dashboard, `ahorro_declarado_usd` se parte en dos columnas que no se pisan,
`ahorro_registrado_usd` (lo apartado que no es inversión) e `inversion_usd`, más un gráfico nuevo
apilado. En el reporte quincenal, el rubro Ahorro sale de los totales de gasto y tiene su propio
bloque desglosado por subcategoría, y el estado del mes agrega una línea con lo ya apartado.
`domain/indicador.py` expone el desglose completo (`ahorro_por_subcategoria`), así que no hace
falta tocar nada si mañana agregan otra subcategoría al rubro.

## Consecuencias
"Gastaron X" en el reporte ahora es solo Necesidades + Deseos: más honesto, pero distinto de
`marcelo_usd`/`nikole_usd` del Dashboard, que siguen siendo todo lo que subió cada uno. El nombre
"Inversión" se reconoce por texto (tolerante a tildes y mayúsculas): si la renombran en la pestaña
`Categorias`, la columna `inversion_usd` queda en cero y su plata pasa a `ahorro_registrado_usd`,
sin perder ningún total. Cambiar las columnas del Dashboard obliga a correr `create_sheet.py` y
`recalc_dashboard.py` una vez.
