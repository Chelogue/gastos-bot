# 0004 — El Google Sheet es la base de datos

**Fecha:** 2026-09-10 · **Estado:** aceptada

## Contexto
Dos usuarios, decenas de gastos por mes, un servicio que escala a cero y un objetivo de costo
≈ 0 USD/mes (G7). Alternativas: Cloud SQL o Firestore como fuente de verdad y el Sheet como vista
exportada; o el Sheet directamente como base de datos, que además es lo que ellos abren y editan.

## Decisión
El Sheet es la única fuente de verdad: pestañas mensuales como tablas de gastos, `Config` y
`Categorias` como configuración editable a mano, `Pendientes` como staging (ADR 0003) y
`Dashboard` como tabla derivada mantenida por el bot (ADR 0005). El código nunca asume
posiciones fijas más allá del encabezado: busca por nombre de columna y por (tipo, clave).
Las lecturas de configuración se cachean 5 min; los escritos son append o reescritura de una fila.

## Consecuencias
Cero infraestructura extra y edición manual trivial; el usuario puede corregir cualquier celda.
A cambio: latencia de ~300–800 ms por llamada, cuota de la API (300 lecturas/min por proyecto,
holgada para este uso), y sin transacciones: el orden Drive → Sheets → Dashboard con rollback de
Drive (R16) es la única garantía de consistencia. Si el volumen creciera a miles de filas por
mes o a más usuarios, migrar a Firestore manteniendo los repos de `storage/` como frontera.
