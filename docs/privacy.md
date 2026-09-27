# Política de privacidad de gastos-bot

**Última actualización: 27 de septiembre de 2026**

gastos-bot es un bot privado de Telegram para registrar gastos del hogar. No ofrece registro
público ni vende datos personales.

## Datos que procesa

El bot recibe el identificador y nombre de Telegram, mensajes y fotos que sus usuarios le envían.
Las fotos pueden mostrar información personal o de pagos. El bot extrae datos del gasto —por
ejemplo fecha, comercio, descripción, moneda e importe— y los guarda junto con la foto de respaldo.

## Cómo se usan y dónde se guardan

Los mensajes y las fotos se usan para proponer y registrar gastos, y para generar resúmenes del
hogar. El texto y las imágenes enviados para extraer datos se procesan con el proveedor de modelos
de lenguaje configurado para el servicio. Las fotos se guardan en Google Drive y los gastos en
Google Sheets de la cuenta Google que autorizó el bot. Google Cloud aloja el servicio y sus logs
técnicos. Telegram transporta los mensajes entre los usuarios y el bot.

Los registros de gastos y fotos quedan guardados hasta que el titular los borre. Los gastos que
quedan como borrador sin confirmar vencen según la configuración del bot (48 horas por defecto).

## Acceso y eliminación

El acceso al bot está restringido a las cuentas de Telegram configuradas por sus administradores.
El titular puede borrar las fotos desde Google Drive y los gastos desde Google Sheets. Para pedir
ayuda con una eliminación, escribe a los administradores en el chat del bot.

El bot no usa estos datos para publicidad ni los vende. Google, Telegram y el proveedor de modelos
pueden procesarlos para prestar sus servicios, de acuerdo con sus propias políticas de privacidad.
