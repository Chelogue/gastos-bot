# PRD — Bot de Telegram para registro y reporte de gastos en pareja

**Versión:** 1.0 · **Fecha:** 2026-09-09 · **Estado:** aprobado para construcción
**Nombre de trabajo:** `gastos-bot`

---

## 1. Problema

Marcelo y Nikole no tienen hoy ningún registro de sus gastos. Los comprobantes (fotos de facturas, capturas de débitos de tarjeta) se quedan en el celular de cada uno y nunca llegan a un lugar común. Sin registro no hay forma de saber cuánto gastan por quincena, en qué, ni si el nivel de gasto es sano respecto a lo que ganan.

**Lo que resuelve este producto:** convertir el gesto más simple posible (mandar una foto por Telegram) en un archivo ordenado en Drive, una fila en Google Sheets, un dashboard con la evolución mes a mes y un reporte quincenal con un indicador de salud financiera (regla 50/30/20). El bot organiza y reporta; no calcula deudas entre ellos ni decide nada.

## 2. Objetivos

| # | Objetivo | Cómo lo medimos |
|---|----------|-----------------|
| G1 | Registrar un gasto cuesta **una foto y un par de toques** (< 15 s de atención) | Tiempo entre envío y ✅ |
| G2 | **Cero entrada manual de datos**: monto, fecha, comercio, moneda y categoría los propone el bot | ≥ 85 % de registros guardados sin editar ningún campo |
| G3 | **Todo comprobante queda archivado** en Drive, en la carpeta del mes y de quien lo subió | 100 % de filas con link a su imagen |
| G4 | **Reporte quincenal automático** con totales e indicador 50/30/20 en USD | Enviado los días 1 y 16 sin intervención |
| G5 | **Dashboard siempre al día** que muestre la evolución de la eficiencia (tasa de ahorro) mes a mes | Tabla mensual recalculada en cada cambio |
| G6 | **Nada se guarda sin confirmación** explícita | 0 filas escritas sin ✅ |
| G7 | Costo total **≈ 0 USD/mes** (free tiers de Cloud Run y LLM) | Factura mensual < 2 USD |

## 3. No-objetivos

- **Reparto / quién le debe a quién.** No hay cálculo de saldos. `compartido` y `quien_subio` quedan registrados para que ellos hagan lo que quieran con la hoja.
- **Alertas en tiempo real** cuando un rubro se pasa. El 50/30/20 vive en el reporte y el dashboard. (P2)
- **Verificar que no falte ningún comprobante** (conciliación, recordatorios). Responsabilidad de ellos.
- **Integración bancaria** (APIs, scraping de email).
- **Más de dos usuarios.**
- **Conversión de monedas distintas de UYU/USD.** Ver D3.

## 4. Usuarios

Dos personas con permisos idénticos, identificadas por su ID de Telegram, que comparten un Google Drive:

| Persona | Ingreso mensual (referencia, en `Config`) |
|---|---|
| Marcelo | 130.000 UYU |
| Nikole | 3.100 USD |

## 5. Historias de usuario

**Registro**
1. Como usuario, quiero **mandar una foto o captura** y que el bot extraiga monto, moneda, fecha y comercio, y proponga una categoría, sin tipear nada.
2. Como usuario, quiero que el bot **siempre me pregunte si el gasto es compartido o personal**, porque eso no está en la factura.
3. Como usuario, quiero **ver lo que entendió y confirmar con un toque**, o corregir categoría, monto, moneda o fecha con botones.
4. Como usuario, quiero **registrar por texto** ("450 uyu farmacia") cuando no tengo comprobante.
5. Como usuario, quiero que la **imagen se archive sola en Drive**, en la carpeta del mes y con mi nombre, con un nombre que diga qué es sin abrirla.

**Consulta y corrección**
6. Como usuario, quiero preguntar **"¿cuánto llevamos?"** y ver la quincena en curso por persona, categoría y moneda.
7. Como usuario, quiero **ver los últimos registros y borrar o editar uno** desde el chat.

**Reporte y evolución**
8. Como pareja, queremos **recibir los días 1 y 16 un reporte** con totales por persona, categoría y moneda, y el **indicador 50/30/20**.
9. Como pareja, queremos abrir el Sheet y **ver en la primera pestaña cómo evoluciona nuestra tasa de ahorro** mes a mes, sin armar nada a mano.

**Casos borde**
10. Foto que **no es un comprobante o es ilegible** → el bot lo dice y no inventa datos.
11. **UYU vs USD ambiguo** ("$") → pregunta antes de habilitar Guardar.
12. **Álbum de varias fotos** → un gasto por imagen.
13. **Compra en cuotas, devolución, moneda extranjera** → ver D1–D3.
14. **Remitente ajeno** → silencio absoluto.

## 6. Decisiones de producto (fugas cerradas)

| ID | Tema | Decisión por defecto |
|----|------|----------------------|
| D1 | **Cuotas** | Se registra lo que dice el comprobante. Factura de compra → total. Captura del débito mensual → esa cuota, con nota `cuota 3/12` (el LLM la detecta si aparece). Regla para los usuarios: **un comprobante por gasto**, no la factura y luego cada débito. |
| D2 | **Devoluciones / reembolsos** | Montos negativos permitidos. El LLM marca `tipo_doc = reembolso`; la tarjeta lo muestra en rojo. Restan del rubro. |
| D3 | **Monedas distintas de UYU/USD** | El bot guarda moneda y monto original en `nota` y pide el monto en USD por mensaje. No inventa tipo de cambio. `moneda = USD`. |
| D4 | **Reenvíos de Telegram** | Cada `update_id` se procesa una sola vez (se guarda en `Pendientes`/memoria de instancia con ventana de 24 h). |
| D5 | **Pendientes sin confirmar** | Expiran a las 48 h. Tocar un botón vencido responde "expiró, reenvía la foto". |
| D6 | **Seguridad del webhook** | Telegram envía `X-Telegram-Bot-Api-Secret-Token`; se verifica en cada request. Los endpoints `/jobs/*` solo aceptan tokens OIDC de Cloud Scheduler. |
| D7 | **Calidad de imagen** | Telegram comprime fotos. `/ayuda` explica que facturas largas conviene enviarlas "como archivo". Se aceptan ambos. |
| D8 | **Ingresos cambian** | `Config` tiene ingreso por persona con `vigente_desde`. El indicador de cada mes usa el ingreso vigente ese mes. |
| D9 | **Dashboard** | Lo mantiene el bot: una fila por mes recalculada en cada alta/edición/borrado. Sin fórmulas `INDIRECT` a pestañas dinámicas. Gráficos leen de esa tabla. |
| D10 | **Tope quincenal** | El reporte del día 16 compara contra el **tope mensual completo** (muestra cuánto margen queda). |
| D11 | **Ahorro** | Residual: ingreso − necesidades − deseos. Si registran movimientos del rubro Ahorro, el reporte muestra también el ahorro declarado. |
| D12 | **Zona horaria** | America/Montevideo para todo (reporte, `fecha_envio`, quincenas). |
| D13 | **Chats de grupo** | El bot ignora updates que no sean chat privado con uno de los dos IDs. |

## 7. Requerimientos

### P0 — Sin esto no se lanza

| ID | Requerimiento | Criterios de aceptación |
|----|---------------|-------------------------|
| R1 | **Recepción** de imágenes (foto o documento) y texto en chat privado | JPG/PNG/HEIC/WebP; álbum → un gasto por imagen; PDF de una página aceptado como imagen |
| R2 | **Extracción con LLM multimodal** en una llamada: monto (puede ser negativo), moneda, fecha, comercio, `tipo_doc` (factura / debito / reembolso / otro), últimos 4 dígitos de tarjeta si aparecen, texto de cuota si aparece, subcategoría sugerida (de la lista fija) y confianza por campo | JSON validado por esquema Pydantic. Prompt con regla explícita: "$" = UYU, "U$S"/"USD" = USD; confianza baja en moneda → `moneda = ambigua`. `tipo_doc = otro` → "no parece un comprobante", sin pendiente |
| R3 | **Tarjeta de confirmación** en dos pasos. Paso 1 obligatorio: 👥 Compartido / 👤 Personal. Paso 2: resumen + ✅ Guardar · ✏️ Categoría · ✏️ Monto · ✏️ Moneda · 📅 Fecha · ❌ Descartar | Guardar deshabilitado hasta resolver compartido/personal y moneda ambigua. Categoría muestra las subcategorías activas agrupadas por rubro. Monto/fecha piden un mensaje de respuesta (ForceReply) |
| R4 | **Archivo en Drive** al confirmar: `Gastos/YYYY-MM/<Nombre>/YYYY-MM-DD_Comercio_1250-UYU.jpg` | Mes y fecha del nombre = fecha de envío. Carpetas creadas si no existen (IDs cacheados en `Config`). Comercio en slug ASCII; colisión → `-2`, `-3`. Reembolso → `_R` antes de la extensión |
| R5 | **Escritura en Sheets** en la pestaña del mes de envío (`2026-09`) con el esquema de §9 | Pestaña creada desde plantilla si no existe, insertada **después** de `Dashboard` y en orden cronológico. Fila visible < 5 s tras ✅. `quien_subio` sale del ID de Telegram, nunca del LLM. `monto_usd` con el TC del mes |
| R6 | **Categorías fijas** en `Categorias` (subcategoría, rubro, activa) | Editar la pestaña cambia botones y prompt sin redeploy (caché de 5 min). El LLM solo sugiere de esa lista |
| R7 | **Tipo de cambio mensual automático**: día 1 a las 00:05 el job `/jobs/fx` consulta una API pública de cotizaciones y guarda UYU/USD en `Config` con fecha | Todas las conversiones del mes usan ese valor. Si la API falla → reutiliza el anterior y avisa por Telegram. Editable a mano en `Config`; si se edita, el bot recalcula `monto_usd` y el Dashboard del mes |
| R8 | **Indicador 50/30/20** en USD sobre ingreso conjunto (ingresos vigentes de `Config`, UYU convertido con TC del mes) con todos los gastos activos, compartidos y personales | Topes: Necesidades 50 %, Deseos 30 %, Ahorro 20 % (porcentajes editables en `Config`). Gastado por rubro = Σ `monto_usd` de subcategorías del rubro. Ahorro según D11 |
| R9 | **Reporte quincenal** días 1 y 16 a las 09:00 UYT, a ambos, vía `/jobs/reporte` | Día 16: gastos 1–15 + avance del mes vs. topes. Día 1: gastos 16–fin + cierre del mes vs. topes. Contenido: total por persona, por subcategoría, por moneda (UYU y USD separados + total USD), indicador por rubro (gastado / tope / %), tasa de ahorro, link al Sheet y a la carpeta del mes |
| R10 | **Dashboard** como primera pestaña: tabla mensual mantenida por el bot + gráficos | Columnas en §9. Se recalcula la fila del mes afectado en cada alta/edición/borrado y al cerrar el mes. Gráficos: tasa de ahorro mensual (línea), gastado por rubro vs. tope (barras), total por persona (barras apiladas) |
| R11 | **Registro por texto** ("450 uyu farmacia", "-300 uyu devolución super") | Misma tarjeta; `link_imagen` vacío; `tipo_doc = texto` |
| R12 | **Consultas**: `/total` y lenguaje natural "cuánto llevamos" → quincena en curso por persona, subcategoría y moneda + avance de rubros; `/ultimos` → últimos 10 con ID | < 5 s |
| R13 | **Corregir / borrar**: `/borrar <id>` y `/editar <id>` | Borrar marca `estado = eliminado` con confirmación; no borra fila ni imagen. Editar reescribe la fila, registra `fecha_modificacion` y recalcula Dashboard |
| R14 | **Seguridad** (D6, D13): dos IDs en `Config`, secret token de Telegram, OIDC en jobs, secretos en Secret Manager | Cualquier otro remitente → silencio; request sin token válido → 403 |
| R15 | **Disponibilidad 24/7 sin servidor permanente**: webhook → Cloud Run con `min-instances=0` | Arranque en frío < 3 s. Timeout de request 120 s. Jobs disparados por Cloud Scheduler |
| R16 | **Fallos**: LLM, Drive o Sheets caídos → mensaje claro y reintento reenviando | Orden Drive → Sheets → Dashboard. Si Sheets falla, se borra el archivo de Drive. Nunca queda fila sin imagen ni imagen sin fila. Errores en Cloud Logging con `update_id` |
| R17 | **Modelo LLM configurable** por variables de entorno (`LLM_PROVIDER`, `LLM_MODEL`) con una interfaz común | Cambiar Gemini ↔ Claude ↔ DeepSeek sin tocar código de negocio |
| R18 | **Idempotencia** (D4) | Un `update_id` repetido responde 200 sin reprocesar |
| R19 | **Set de evaluación**: 30 comprobantes reales con ground truth y script que mide precisión por campo | Bake-off reproducible entre proveedores antes de fijar el default |

### P1 — Fast-follow

| ID | Requerimiento |
|----|---------------|
| R20 | Detección de duplicados: mismo monto + fecha + comercio similar en 3 días → "parece duplicado, ¿guardar igual?" |
| R21 | Nota opcional desde el caption de la foto (además de cuota/moneda original) |
| R22 | `/reporte` a demanda (quincena actual, anterior o mes) |
| R23 | Gastos recurrentes (alquiler, suscripciones) creados por comando sin foto |
| R24 | `/dashboard` que devuelve la tabla mensual resumida en el chat |

### P2 — No en v1, el diseño no debe impedirlos

- Alertas cuando un rubro supera el 80 % del tope.
- Cálculo de reparto (por eso se guardan `quien_subio` y `compartido`).
- Exportar el reporte como imagen.
- Más usuarios (lista en `Config`).

## 8. Arquitectura

```
[Telegram] --webhook + secret token--> [Cloud Run: FastAPI + python-telegram-bot, Python 3.12]
                                            │         │          │
                                            │         │          └──> [LLM multimodal]   JSON validado
                                            │         └─────────────> [Google Drive API] Gastos/YYYY-MM/<Nombre>/
                                            └───────────────────────> [Google Sheets API] Dashboard · YYYY-MM · Config · Categorias · Pendientes

[Cloud Scheduler] --día 1 00:05 UYT, OIDC--> /jobs/fx
[Cloud Scheduler] --1 y 16 09:00 UYT, OIDC--> /jobs/reporte
[Secret Manager] --> TELEGRAM_TOKEN, TELEGRAM_SECRET, LLM_API_KEY, SA credentials (o SA nativa de Cloud Run)
[GitHub] --push main--> [GitHub Actions + Workload Identity] --> [Artifact Registry] --> [Cloud Run]
```

**Decisiones técnicas**

- **Webhook, no polling.** Cloud Run escala a cero; solo corre cuando Telegram o Scheduler llaman.
- **Sin OCR separado.** El LLM multimodal lee la imagen y devuelve JSON en una llamada.
- **LLM por defecto: Gemini Flash** (precio, free tier, misma cuenta de Google). Candidatos del bake-off R19: DeepSeek V4 Flash Vision (más barato, experimental, datos a servidores en China) y Claude Haiku (más caro, muy fiable). Se elige con el resultado del script.
- **Sin base de datos.** El Sheet es la base de datos; `Pendientes` es el staging; el `callback_data` lleva solo el ID del pendiente.
- **Service account de Cloud Run** con Drive y Sheets compartidos a su email. Sin OAuth de usuario, sin JSON keys en el repo (Workload Identity Federation para el deploy).
- **Stack:** `uv`, FastAPI, `python-telegram-bot` v21 (webhook), `gspread`, `google-api-python-client` (Drive), `pydantic` + `pydantic-settings`, `structlog`, `pytest`, `ruff`.

## 9. Google Sheet

Orden de pestañas: `Dashboard` · `2026-09` · `2026-10` · … · `Config` · `Categorias` · `Pendientes` (las tres últimas ocultas por defecto).

**`Dashboard`** — tabla mantenida por el bot, una fila por mes:

| Columna | Descripción |
|---|---|
| `mes` | `2026-09` |
| `tc_uyu_usd` | TC fijado el día 1 |
| `ingreso_usd` | Ingreso conjunto convertido |
| `necesidades_usd` · `necesidades_pct` · `necesidades_tope_usd` | Gastado, % del ingreso, tope 50 % |
| `deseos_usd` · `deseos_pct` · `deseos_tope_usd` | Ídem 30 % |
| `ahorro_residual_usd` · `ahorro_pct` | Ingreso − necesidades − deseos; % del ingreso (**tasa de ahorro = métrica de eficiencia**) |
| `ahorro_declarado_usd` | Σ rubro Ahorro registrado (D11) |
| `marcelo_usd` · `nikole_usd` | Total subido por cada uno |
| `compartido_usd` · `personal_usd` | Por marca |
| `n_registros` · `n_sin_editar_pct` | Volumen y calidad de extracción (G2) |
| `cumplimiento` | ✅ si necesidades ≤ 50 % y deseos ≤ 30 %; ⚠️ si uno se pasa; ❌ si ambos |

Debajo de la tabla: gráficos nativos de Sheets (creados por el script de plantilla) que leen la tabla.

**Pestaña por mes (`2026-09`)**, elegida por fecha de envío:

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | texto | `G-260909-001` |
| `fecha_gasto` | fecha | La del comprobante; si no aparece, la de envío |
| `fecha_envio` | fecha-hora | UYT |
| `quien_subio` | Marcelo / Nikole | Por ID de Telegram |
| `compartido` | sí / no | |
| `comercio` | texto | Normalizado |
| `monto` | número | Negativo si reembolso |
| `moneda` | UYU / USD | |
| `tc_mes` | número | |
| `monto_usd` | número | `monto` si USD; `monto / tc_mes` si UYU |
| `rubro` | Necesidades / Deseos / Ahorro | Derivado de la subcategoría |
| `subcategoria` | texto | |
| `medio_pago` | texto | Opcional |
| `tipo_doc` | factura / debito / reembolso / texto | |
| `nota` | texto | Cuota, moneda original, caption |
| `quincena` | Q1 / Q2 | 1–15 / 16–fin |
| `editado` | sí / no | Si se tocó algún campo antes de ✅ (alimenta `n_sin_editar_pct`) |
| `link_imagen` | URL | |
| `estado` | activo / eliminado | |
| `fecha_modificacion` | fecha-hora | |

**`Config`:** `telegram_id` ↔ `nombre`; `ingreso` por persona con `moneda` y `vigente_desde`; `tc_uyu_usd` con `fecha`; `zona_horaria`; `hora_reporte`; `pct_necesidades / deseos / ahorro`; IDs de carpetas de Drive cacheados.
**`Categorias`:** `subcategoria`, `rubro`, `activa`.
**`Pendientes`:** `pendiente_id`, `update_id`, `telegram_id`, `json_extraccion`, `file_id`, `creado`, `expira`.

## 10. Categorías iniciales

| Rubro | Subcategorías |
|---|---|
| **Necesidades (50 %)** | Vivienda · Servicios · Supermercado · Transporte · Salud · Educación · Cuotas y seguros |
| **Deseos (30 %)** | Restaurantes y delivery · Ocio · Suscripciones · Viajes · Compras · Cuidado personal · Regalos |
| **Ahorro (20 %)** | Ahorro · Inversión · Pago extra de deuda |

## 11. Métricas de éxito

**Adelantadas (2 semanas):** ≥ 85 % de registros con ✅ sin editar (`n_sin_editar_pct`); p95 foto → tarjeta < 10 s; 0 filas sin ✅; 0 duplicados por reenvío.
**Rezagadas (3 meses):** Dashboard con 3 filas completas sin intervención manual; reportes entregados 6/6; costo mensual < 2 USD; ellos pueden responder "¿mejoró nuestra tasa de ahorro?" mirando una sola pestaña.

## 12. Preguntas abiertas

| Pregunta | Quién | ¿Bloquea? |
|----------|-------|-----------|
| Fuente concreta del TC (BCU si expone API; si no, API pública de cotizaciones). Se decide en implementación | Claude Code | No |
| Confirmar D1–D13 o ajustarlas | Marcelo | No (se construye con los defaults) |
| Aportar los 30 comprobantes del set de evaluación | Marcelo y Nikole | Sí, para R19 |

## 13. Fases

**Fase 0 — Infra y plantilla.** Proyecto GCP, service account, Secret Manager, Artifact Registry, Cloud Run vacío con `/health`, GitHub Actions con Workload Identity, script que crea el Sheet con todas las pestañas y gráficos, carpeta `Gastos/` en Drive. Bot responde `/start` solo a los dos IDs.

**Fase 1 — Núcleo (R1–R6, R14–R19).** Foto → extracción → tarjeta → Drive → fila. Bake-off de modelos con el set de evaluación. Dashboard se actualiza con `monto_usd` provisional (TC manual en `Config`).

**Fase 2 — Dinero, reporte y dashboard (R7–R10).** Job de TC, cálculo 50/30/20, reporte quincenal, Dashboard completo.

**Fase 3 — Consulta y corrección (R11–R13).** Texto, `/total`, `/ultimos`, editar/borrar.

**Fase 4 — Pulido (P1).**

Usar la Fase 1 dos semanas con datos reales antes de construir la Fase 2, para que el indicador nazca sobre categorías ya ajustadas.
