# Set de evaluación (R19 del PRD)

Poner aquí 30 comprobantes reales. Las imágenes están gitignored (son datos financieros); solo se versiona este README y `../ground_truth.json`.

Cobertura mínima recomendada:
- 10 capturas de notificaciones de débito (distintos bancos y apps)
- 10 fotos de facturas de papel (supermercado, restaurante, farmacia, servicios)
- 5 con montos en USD ("U$S")
- 3 con "$" ambiguo donde un humano dudaría
- 2 que NO son comprobantes (para verificar que el bot los rechaza)

Nombrar `01.jpg` … `30.jpg`. Para cada uno, una entrada en `ground_truth.json`:

```json
{
  "01.jpg": {
    "monto": 1250.00,
    "moneda": "UYU",
    "fecha": "2026-09-03",
    "comercio": "Disco",
    "tipo_doc": "factura",
    "subcategoria": "Supermercado"
  }
}
```

Correr: `uv run python tests/evals/run_extraction_eval.py --provider gemini`
