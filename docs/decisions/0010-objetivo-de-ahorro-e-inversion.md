# 0010 — Dos indicadores: el gasto que no hay que pasar y el objetivo que sí

**Fecha:** 2026-09-11 · **Estado:** aceptada (pedido de Marcelo; extiende R8)

## Contexto
El 50/30/20 del PRD trata a los tres rubros igual, pero no lo son. Pasarse en Necesidades o Deseos
es un problema; apartar más del 20 % es exactamente lo que uno quiere. Hasta ahora el Dashboard
mostraba el tope de Necesidades y el de Deseos, pero el 20 % de ahorro no aparecía por ningún
lado: sin objetivo a la vista, lo invertido era un número suelto imposible de leer como KPI.
Marcelo lo pidió así: quiere ver lo que ya se ejecutó en el portafolio y celebrar cuando se pasan.

## Decisión
`domain/indicador.py` suma el objetivo del mes (20 % del ingreso, el porcentaje sale de `Config`),
cuánto de ese objetivo ya se ejecutó (`ejecutado_pct` sobre el rubro Ahorro completo) y un estado
propio, `Ejecucion`: 🟡 en camino, 🎯 cumplido, 🚀 superado. Convive con `Cumplimiento`, que sigue
mirando solo el gasto: son dos preguntas distintas y cada una tiene su columna en el Dashboard.
La inversión se sigue midiendo aparte del resto del rubro (ADR 0008), y se agrega qué porcentaje
de lo apartado terminó en el portafolio: ese es el número que se quiere empujar, sin castigar al
fondo de emergencia ni al pago extra de deuda, que van antes que invertir.

## Consecuencias
El Dashboard pasa a 23 columnas, que es mucho para leer a ojo pero es justo lo que necesita una
herramienta de tablero conectada al Sheet. Pasarse del objetivo no cambia `cumplimiento`: un mes
puede tener 🚀 en ejecución y ❌ en gasto al mismo tiempo, y está bien que se vean los dos. Si
algún día quieren que el KPI sea solo lo invertido en portafolio y no todo el rubro, se cambia
qué numerador usa `ejecutado_pct` y nada más.
