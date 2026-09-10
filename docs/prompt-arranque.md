# Prompt de arranque para Claude Code

Antes de pegarlo: crea el repo `gastos-bot` en GitHub, clónalo, copia el PRD a `docs/PRD.md`, copia el contenido de `CLAUDE.md` (está al final de ESTRUCTURA-REPO) a la raíz, y guarda ESTRUCTURA-REPO como `docs/estructura.md`. Abre Claude Code en esa carpeta y pega lo siguiente.

---

Vas a construir `gastos-bot`, un bot de Telegram para que dos personas registren gastos en Google Sheets y Drive y reciban un reporte quincenal con la regla 50/30/20. Todo lo que necesitas saber del producto está en `docs/PRD.md` y la organización del código está en `docs/estructura.md`. Las reglas de trabajo están en `CLAUDE.md`. Lee los tres archivos completos antes de escribir una sola línea de código.

Cómo quiero trabajar contigo:

1. **Primero entiende, después planifica.** Cuando termines de leer, dame un resumen de máximo 15 líneas de lo que entendiste del producto y señala cualquier ambigüedad o contradicción que encuentres entre el PRD, la estructura y CLAUDE.md. Si algo del PRD no se puede implementar como está escrito, dímelo ahora, no cuando estés a mitad de camino.

2. **Plan de la Fase 0 y la Fase 1** (PRD §13). Preséntalo como una lista ordenada de tareas pequeñas, cada una con los requerimientos del PRD que cubre (R1, R2…) y los archivos que va a tocar. Espera mi OK antes de empezar.

3. **Construye por tareas, no de golpe.** Cada tarea termina con tests pasando y un commit con mensaje descriptivo. Después de cada tarea, dime en dos líneas qué hiciste y qué sigue. Si una tarea te lleva a tocar más de 5 archivos, para y pregúntame si la partimos.

4. **Empieza por lo puro.** Antes de tocar Telegram, Google o el LLM, deja `src/gastos_bot/domain/` completo y testeado: modelos, quincenas, categorías, nombres de archivo, IDs, conversión de moneda e indicador 50/30/20. Es la parte que no cambia y la que más vale tener bien.

5. **Los adaptadores externos van con dobles de prueba.** Cuando implementes `extraction/`, `storage/` y `bot/`, escribe primero la interfaz y un fake para tests; el cliente real va después. Quiero poder correr `uv run pytest` sin red y sin credenciales.

6. **Infra como scripts idempotentes.** `infra/setup_gcp.sh` y `scripts/create_sheet.py` se tienen que poder correr dos veces sin romper nada. Antes de escribirlos, explícame qué APIs de GCP vas a habilitar, qué permisos necesita la service account y qué costos (si alguno) implican.

7. **Cosas que no haces sin preguntarme:** desplegar a Cloud Run, registrar o cambiar el webhook de Telegram, crear recursos de GCP que cuesten dinero, agregar una dependencia que no esté en `docs/estructura.md`, o cambiar el esquema del Sheet.

8. **Decisiones no triviales → ADR** en `docs/decisions/`. Ya sé que vas a tener que decidir cosas que el PRD no cubre (cómo cachear IDs de carpetas, cómo estructurar el `callback_data`, qué API usar para el tipo de cambio). Decide, escríbelo en 10 líneas y sigue; no me preguntes por cada detalle menor, solo por los de la lista del punto 7 y por lo que contradiga el PRD.

9. **Al terminar la Fase 1**, entrégame: instrucciones para correr en local con `scripts/run_local.sh`, instrucciones para el primer deploy, y el script de evaluación listo para que yo ponga los 30 comprobantes en `tests/fixtures/comprobantes/` y corra el bake-off. Actualiza la sección "Estado" de `CLAUDE.md`.

Datos que ya puedes dar por ciertos: los dos usuarios son Marcelo y Nikole; monedas UYU y USD; zona horaria America/Montevideo; hosting Cloud Run; LLM por defecto Gemini Flash, intercambiable por variable de entorno. Los IDs de Telegram, el ID del Sheet y las credenciales te los daré cuando lleguemos a esa tarea; mientras tanto usa placeholders en `.env.example`.

Empieza por el punto 1.
