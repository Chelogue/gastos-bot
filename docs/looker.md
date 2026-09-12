# Tablero en Looker Studio

El Sheet es la base de datos; Looker Studio es la pantalla linda. Es gratis, lee el Sheet directo
y anda bien en el celular. Se arma una sola vez y después se actualiza solo.

## Qué conectar

| Fuente | Pestaña | Para qué |
|---|---|---|
| Detalle | `Movimientos` | Todo gasto de todo mes, en vivo (ADR 0011). Filtros por persona, rubro, categoría y fecha |
| Mensual | `Dashboard` | Una fila por mes: topes, objetivo de ahorro, ejecutado, cumplimiento |

`Movimientos` es una sola fórmula que apila las pestañas de mes y deja afuera los gastos borrados,
así el tablero da lo mismo que el Dashboard. No hay que tocarla: cuando el bot abre el mes nuevo,
la reescribe.

## Armarlo (10 minutos, una sola vez)

1. Entrá a [lookerstudio.google.com](https://lookerstudio.google.com) con la cuenta que es dueña
   del Sheet y creá un informe en blanco.
2. Elegí el conector **Google Sheets**, buscá el archivo **Gastos** y seleccioná la hoja
   **Movimientos**. Dejá marcado "Usar la primera fila como encabezados" y agregá la fuente.
3. Repetí *Agregar datos* para la hoja **Dashboard**.
4. En *Recurso → Administrar fuentes de datos → Editar*, revisá los tipos: `fecha_gasto` y
   `fecha_envio` como fecha, `monto`, `monto_usd` y todo lo que termina en `_usd` como número, y
   los que terminan en `_pct` como porcentaje. Looker casi siempre acierta; los porcentajes son
   los que a veces entran como número suelto.
5. Agregá un **control de período** sobre `fecha_gasto` y un **filtro desplegable** por
   `quien_subio` y por `rubro`. Con eso ya podés cortar todo el tablero.

## Qué poner arriba

La pregunta de los cinco segundos es "cómo venimos este mes". Sugerencia de orden:

1. **Cuatro tarjetas** (gráfico *Tarjeta de puntuación* sobre `Dashboard`, filtrado al último mes):
   ingreso, necesidades, deseos y **ejecutado vs objetivo**. La última es la del KPI: si pasa de
   100 % se pasaron del 20 % presupuestado, que es exactamente lo que se busca.
2. **Barras apiladas** sobre `Dashboard` por mes: `ahorro_registrado_usd` e `inversion_usd`, con
   `ahorro_objetivo_usd` como serie de referencia. Ahí se ve la parte que efectivamente fue al
   portafolio contra lo que se había presupuestado.
3. **Serie temporal** sobre `Dashboard`: `necesidades_pct` y `deseos_pct` con líneas de referencia
   en 50 % y 30 %.
4. **Barras horizontales** sobre `Movimientos`: `monto_usd` por `subcategoria`, ordenado de mayor a
   menor, filtrado al mes en curso. Es el "en qué se nos va".
5. **Tabla** sobre `Movimientos` con fecha, comercio, monto, categoría y quién, para cuando quieren
   ver el detalle sin abrir el Sheet.

## Cosas que conviene saber

- Looker cachea los datos unos 15 minutos. Si acabás de registrar un gasto y no aparece, tocá
  *Actualizar datos* (el ícono de refrescar arriba a la derecha).
- Compartir el informe con Nikole es el mismo botón de compartir de Drive, sin costo.
- Si alguna vez el tablero aparece vacío, revisá que `Movimientos!A2` siga teniendo la fórmula:
  se repone corriendo `uv run python scripts/create_sheet.py`.
- El tablero no escribe nada: se puede romper y rehacer sin riesgo para los datos.
