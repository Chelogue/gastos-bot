# 0005 — Dashboard mantenido por el bot, no por fórmulas

**Fecha:** 2026-09-10 · **Estado:** aceptada (fija D9 del PRD)

## Contexto
El Dashboard necesita una fila por mes con totales por rubro, persona y marca, más el 50/30/20.
Con fórmulas habría que apuntar a pestañas cuyo nombre cambia cada mes (`INDIRECT`), que son
frágiles, lentas de recalcular y se rompen si alguien renombra una pestaña.

## Decisión
`storage/dashboard.py` reescribe la fila del mes afectado en cada alta, edición o borrado, a
partir de `domain/indicador.calcular()` sobre todas las filas activas del mes. Los porcentajes se
guardan como fracción (0.42) con formato de porcentaje en la celda. Los gráficos nativos leen
esa tabla. `scripts/recalc_dashboard.py` recalcula todos los meses a mano (p. ej. tras editar el
TC en `Config`, R7).

## Consecuencias
La tabla es datos puros: se puede copiar, graficar o exportar sin dependencias. Si alguien edita
una fila de un mes a mano en la pestaña mensual, el Dashboard queda desactualizado hasta el
próximo movimiento o hasta correr el script; se documenta en el runbook. El cálculo en Python es
el mismo que usa el reporte quincenal (R9), así nunca discrepan.
