# 0014 — Lotes de gastos desde una sola imagen

**Fecha:** 2026-09-23 · **Estado:** aceptada

## Contexto

Una captura de la aplicación de una tarjeta puede mostrar varios débitos independientes. El flujo
anterior exigía recortar o reenviar la misma captura una vez por movimiento, duplicaba el archivo
en Drive y hacía una escritura y un recálculo del Dashboard por cada gasto.

## Decisión

La extracción de imágenes devuelve una lista ordenada de uno a diez movimientos. Una lista de un
elemento conserva el flujo existente; con dos o más se crea un lote en `Pendientes`, sin agregar
columnas al Sheet. Telegram reutiliza una tarjeta para revisar cada movimiento: permite corregir
los campos habituales y el comercio, aplicar compartido/personal y moneda a los restantes, omitir
un movimiento o agregar uno manualmente. Las fechas relativas se interpretan respecto de la fecha
del mensaje.

Cada movimiento se contrasta por fecha, comercio, monto, moneda y creador contra los gastos ya
guardados. Después de revisar todos, una pantalla final permite reabrir cualquiera o confirmar el
lote. La confirmación sube una sola imagen cuyo nombre contiene `multiple`, agrega todas las filas
en una única operación de Sheets, comparte el mismo enlace y recalcula el Dashboard una vez. Si
Sheets falla, se elimina la imagen subida. Luego cada gasto ofrece por separado las opciones de
único o recurrente.

## Consecuencias

El JSON persistido en `Pendientes` incorpora identidad, posición y estado del lote, pero no hay una
migración visible de la planilla. La escritura agrupada reduce llamadas y evita imágenes
duplicadas. El flujo mantiene confirmación explícita antes de cualquier alta; a cambio, la
orquestación de Telegram debe conservar el progreso y permitir reabrir elementos hasta 48 horas.
El límite de diez mantiene legibles los teclados y acota la salida del modelo.
