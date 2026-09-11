# 0007 — Fuente del tipo de cambio: open.er-api.com, con el anterior como red de seguridad

**Fecha:** 2026-09-11 · **Estado:** aceptada (cierra la pregunta abierta del PRD §12, R7)

## Contexto
El día 1 de cada mes hay que fijar un UYU/USD y usarlo para todas las conversiones del mes (D8).
El BCU es la fuente oficial, pero su servicio de cotizaciones es SOAP (`wscotizaciones`) y el
endpoint que usa su web es interno y no documentado: probado el 2026-09-11 responde
«Input string was not in a correct format» ante un payload razonable. Sostener un cliente SOAP
o adivinar un contrato privado es mucho costo para un número que solo ordena gastos de casa.

## Decisión
`jobs/fx_job.py` consulta `https://open.er-api.com/v6/latest/USD` (exchangerate-api, gratis, sin
API key, actualización diaria) y toma `rates.UYU` redondeado a dos decimales. La URL vive en
`FX_API_URL`, así que cambiar de fuente no toca código. La fuente es un adaptador detrás del
Protocol `FuenteTC`; agregar el BCU más adelante es escribir otra clase.
Si la fuente falla, el job reusa el TC del mes anterior, lo anota en `Config` y avisa por
Telegram; si tampoco hay anterior, avisa y no inventa ningún número.

## Consecuencias
El TC es de mercado, no el interbancario oficial del BCU: para un presupuesto doméstico la
diferencia (décimas de peso) no cambia ninguna decisión, y el valor queda visible y editable en
`Config`. Si algún día quieren el oficial, se escribe `BcuTC` y se cambia una variable. Editar el
TC a mano sigue siendo la última palabra: `scripts/recalc_dashboard.py` reconvierte el mes.
