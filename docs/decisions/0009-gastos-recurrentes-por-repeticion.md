# 0009 — Gastos recurrentes: repetir uno existente, no plantillas en Config

**Fecha:** 2026-09-11 · **Estado:** aceptada (R23)

## Contexto
El alquiler y las suscripciones se pagan todos los meses y casi nunca dejan un comprobante que
valga la pena fotografiar. R23 pide crearlos por comando, sin foto. La opción obvia era guardar
plantillas en `Config` (tipo `recurrente`, con monto, moneda y subcategoría) y un comando que las
instancie. Eso obliga a inventar un formato nuevo dentro de `Config`, a mantenerlo a mano cuando
cambia el alquiler, y a que las plantillas y los gastos reales puedan divergir.

## Decisión
`/repetir <ID>` copia un gasto ya guardado con la fecha de hoy y abre la tarjeta de siempre para
confirmar. No hay configuración: la plantilla es el gasto del mes pasado, que ya tiene monto,
moneda, comercio, categoría y compartido/personal. Si el monto cambió, se corrige con el botón
de siempre antes de guardar. La fila nueva queda con `tipo_doc = texto`, sin imagen, y con
«repetido de G-…» en la nota, así se puede rastrear de dónde salió.

## Consecuencias
Cero configuración y cero formato nuevo en el Sheet, pero hay que tener el ID a mano: sale de
`/ultimos`, o del Sheet si el gasto es viejo. Como la fecha es la de hoy y el original suele ser
del mes pasado, el aviso de duplicados (R20) no se dispara; si alguien repite algo de esta semana,
salta el aviso, que es justo lo que corresponde. Si más adelante quieren nombres («/alquiler»),
se agregan plantillas en `Config` sin tocar nada de esto.
