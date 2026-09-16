# 0012 — Emprendimientos: un rubro aparte, con tope propio y fuera del objetivo de ahorro

**Fecha:** 2026-09-16 · **Estado:** aceptada (pedido de Marcelo; cambia los rubros del PRD §10, D11 y R8)

## Contexto
Marcelo y Nikole le ponen plata a emprendimientos propios, empezando por Polybuk. No había dónde
registrarla: el 15 de septiembre «Inversión marketing Polybuk», 600 USD, terminó cargado como
*Pago extra de deuda*. Con eso el Dashboard decía «Ahorro registrado: 600» y el objetivo del mes
marcaba 167 %, cuando lo que efectivamente fue al portafolio daba 120 %.

No es lo mismo que invertir en el portafolio: es plata ilíquida, sin valor de mercado y que puede
no volver. Si contara para el 20 % (la salida rápida: agregar «Polybuk» como subcategoría de
Ahorro en la pestaña `Categorias`), podrían «superar el objetivo» sin poner un peso en el
portafolio, y el KPI de ADR 0010 dejaría de medir lo que quieren medir. Contarlo dentro de Deseos
tampoco sirve: ensucia ese tope y no es un gusto.

## Decisión
Un cuarto rubro, **Emprendimientos**, con una subcategoría por emprendimiento (hoy solo
Polybuk; uno nuevo es una fila más en `Categorias`, sin tocar código).

- **Tiene tope propio**, `pct_emprendimientos` en `Config` (15 % del ingreso). No forma parte del
  50/30/20 ni de su suma de 100: es un techo aparte. Si un mes Polybuk se come la plata del
  ahorro, el objetivo del 20 % no se cumple y se ve, sin redistribuir nada.
- **Cuenta en `Cumplimiento`** como un tope más: ✅ ninguno pasado, ⚠️ uno, ❌ dos o más. Hoy ⚠️
  ya significaba «se pasó uno», no «cerca del tope», así que un semáforo aparte solo tendría ✅ y
  ❌; mejor un único indicador para todo lo que no hay que pasar.
- **No cuenta para el objetivo de ahorro** (`ejecutado_pct` sigue mirando solo el rubro Ahorro).
- **Sí se descuenta del residual** (D11): ingreso − necesidades − deseos − emprendimientos. Esa
  plata ya no está en casa.
- **En el reporte va en su propio bloque**, como el ahorro (ADR 0008), fuera de «Gastaron X», con
  lo de la quincena y lo acumulado por emprendimiento desde que hay registros. Si un emprendimiento
  devuelve plata, se registra en negativo (D2) y el acumulado baja.
- **Dashboard:** `emprendimientos_usd`, `emprendimientos_pct` y `emprendimientos_tope_usd`, después
  de las de Deseos, y el gráfico «Gastado por rubro vs. tope» suma sus dos series.

El acumulado necesita los meses anteriores. `GastosRepo.listar_anteriores` los lee en una sola
llamada (`values_batch_get`, sin formatear) y solo cuando el mes tiene movimientos de
emprendimientos, así `/total` no se vuelve más lento para nadie más.

## Consecuencias
Los topes suman 115 % del ingreso, y está bien: son techos, no un reparto. El Dashboard pasa a 26
columnas; migrar es `create_sheet.py --reescribir-encabezados` y `recalc_dashboard.py`.

Al agregar columnas en el medio apareció un problema viejo: los gráficos existentes solo se
reubicaban y seguían apuntando a la posición de antes, así que «Total por persona» dibujaba
ahorro e inversión en vez de Marcelo y Nikole desde que se sumaron columnas, y quedaba un
gráfico retirado («Ahorro e inversión (USD)») dibujando cualquier cosa. Ahora `create_sheet.py` reescribe las series de cada gráfico del bot en
cada corrida y borra por título los que el bot dejó de usar (`GRAFICOS_RETIRADOS`); un gráfico
hecho a mano no se toca.

Otro de paso: las lecturas sin formatear pasaban los números a texto antes de parsearlos, y un
0.125 (12,5 %) se leía como «125» por la regla de miles del arreglo anterior. Ahora un número que
llega como número se usa tal cual; la regla de miles queda solo para texto.
