# 0006 — Drive y Sheets con el token OAuth de Marcelo, no con la service account

**Fecha:** 2026-09-10 · **Estado:** aceptada (reemplaza la parte de "sin OAuth de usuario" del PRD §8)

## Contexto
El PRD §8 pedía que la service account de Cloud Run escribiera en Drive y Sheets compartidos a
su email. En la primera prueba real la subida falló con `storageQuotaExceeded`: desde 2025 las
service accounts tienen cuota de almacenamiento cero en Drive (`storageQuota.limit = 0`). Pueden
leer y escribir en carpetas compartidas, pero no ser dueñas de archivos nuevos salvo en Unidades
compartidas, que requieren Google Workspace. Alternativas: (a) subir en nombre de un usuario con
OAuth; (b) guardar imágenes en Cloud Storage y linkearlas (rompe G3); (c) Workspace (~7 USD/mes
por usuario).

## Decisión
(a), elegida por Marcelo el 2026-09-10. Un cliente OAuth "Escritorio" del proyecto, autorizado una
vez con `scripts/autorizar_google.py`, produce un refresh token que vive en `.env` (local) y en
Secret Manager como `GOOGLE_OAUTH_TOKEN_JSON` (Cloud Run). `storage/google_auth.get_credentials`
lo prioriza sobre service account y ADC. La misma credencial se usa para Sheets, así que la
service account deja de necesitar acceso al Sheet y a la carpeta (queda, no molesta). Los archivos
son de Marcelo, contra su cuota de 15 GB, en `Bot Finanzas/YYYY-MM/<Nombre>/`.

## Consecuencias
Cero costo y las imágenes visibles como cualquier archivo de Drive. A cambio, un token de Marcelo
vive en Secret Manager. La app OAuth no puede quedar en estado "Testing": Google expira a los
7 días los refresh tokens de apps externas en pruebas cuando piden scopes como Drive o Sheets.
Debe publicarse como "In production" antes de autorizar el token de producción. Si cambia la
contraseña, Marcelo revoca el acceso o Google invalida el token por otro motivo, hay que
reautorizarlo (runbook). La política de expiración de Google es la causa de la caída del
2026-09-27; el token autorizado el 2026-09-10 expiró después de más de siete días.
