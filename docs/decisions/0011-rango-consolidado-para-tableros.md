# 0011 — Un rango consolidado por fórmula para tableros y tablas dinámicas

**Fecha:** 2026-09-11 · **Estado:** aceptada (habilita Looker Studio; no cambia el PRD §9)

## Contexto
El Sheet guarda una pestaña por mes (PRD §9), que es cómoda para leer y mantiene las filas
acotadas. Pero todo lo que sirve para mirar los datos de otra forma necesita un solo rango: una
tabla dinámica de Sheets lee una sola pestaña, y Looker Studio toma una hoja por fuente de datos.
Con doce pestañas al año, cualquiera de las dos opciones obliga a repetir el trabajo cada mes.
Marcelo quiere el tablero en Looker Studio, así que hacía falta resolverlo.

## Decisión
Una pestaña `Movimientos` cuya celda A2 es una sola fórmula que apila todas las pestañas de mes
(`QUERY` sobre un literal `{…}`) y filtra las filas vacías. No hay copia de datos: lo que se ve es
lo que hay en las pestañas, en vivo, sin importar si la fila la escribió el bot o una persona a
mano. El bot reescribe esa fórmula cuando crea la pestaña de un mes nuevo, que es la única vez que
cambia. El separador de argumentos depende del idioma del Sheet (el de Marcelo está en es_MX), así
que quien la escribe prueba con coma, lee el resultado y si el Sheet la rechazó reescribe con
punto y coma.

## Consecuencias
Looker Studio y las tablas dinámicas apuntan a `Movimientos` y no se tocan nunca más. La fórmula
es un punto único de falla: si alguien la borra, el tablero queda vacío hasta la próxima corrida
de `create_sheet.py` o hasta que aparezca un mes nuevo; el runbook lo explica. Con muchos años de
datos el rango crece, pero son decenas de filas por mes y Sheets lo aguanta de sobra.
