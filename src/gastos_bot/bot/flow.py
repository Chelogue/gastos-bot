"""Orquestación foto → extracción → pendiente → tarjeta → confirmar → Drive → Sheets → Dashboard.

Único lugar que conecta las capas. No conoce a python-telegram-bot: habla con Telegram a través
de ``Mensajero`` (que ``app.py`` implementa) y con Google a través de ``Storage``. Así se testea
entero con dobles (tests/unit/test_flow.py).
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from gastos_bot.bot import keyboards as kb
from gastos_bot.bot import messages as msg
from gastos_bot.domain import ids, naming
from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.fx import a_usd
from gastos_bot.domain.indicador import calcular, ingreso_conjunto_usd
from gastos_bot.domain.models import (
    CampoEsperado,
    EstadoPendiente,
    Gasto,
    Moneda,
    Pendiente,
    Persona,
    TipoDoc,
    TipoDocExtraido,
)
from gastos_bot.domain.parseo import TextoInvalido, parsear_fecha, parsear_monto
from gastos_bot.domain.quincena import a_local, mes_de, quincena_de
from gastos_bot.extraction.base import Entrada, ExtraccionFallida, Extractor
from gastos_bot.logging_setup import bind_context, get_logger
from gastos_bot.storage.base import StorageError
from gastos_bot.storage.factory import Storage

log = get_logger("gastos_bot.flow")


class Mensajero(Protocol):
    """Lo mínimo que el flujo necesita de Telegram."""

    async def enviar(
        self,
        chat_id: int,
        texto: str,
        teclado: kb.Teclado | None = None,
        *,
        force_reply: bool = False,
    ) -> int:
        """Manda un mensaje y devuelve su message_id."""
        ...

    async def editar(
        self, chat_id: int, message_id: int, texto: str, teclado: kb.Teclado | None = None
    ) -> None: ...

    async def descargar(self, file_id: str) -> bytes: ...


def _ahora_utc() -> datetime:
    return datetime.now(UTC)


class Flujo:
    def __init__(
        self,
        *,
        extractor: Extractor,
        storage: Storage,
        mensajero: Mensajero,
        zona: str = "America/Montevideo",
        ttl_horas: int = 48,
        reloj: Callable[[], datetime] = _ahora_utc,
    ) -> None:
        self.extractor = extractor
        self.st = storage
        self.tg = mensajero
        self.zona = zona
        self.ttl = timedelta(hours=ttl_horas)
        self.reloj = reloj

    # ---------- entradas ----------

    async def procesar_imagen(
        self,
        *,
        update_id: int,
        telegram_id: int,
        chat_id: int,
        file_id: str,
        mime: str,
        caption: str | None = None,
    ) -> None:
        with bind_context(update_id=update_id, telegram_id=telegram_id):
            persona = await self._persona(telegram_id, chat_id)
            if persona is None:
                return
            if await self.st.pendientes.update_visto(update_id):
                log.info("update_duplicado")
                return
            ahora = self.reloj()
            try:
                imagen = await self.tg.descargar(file_id)
                catalogo = await self.st.categorias.catalogo()
                extraccion = await self.extractor.extraer(
                    Entrada(imagen=imagen, mime=mime, caption=caption), catalogo.nombres_activos()
                )
            except ExtraccionFallida as exc:
                log.warning("extraccion_fallida", motivo=str(exc))
                await self.tg.enviar(chat_id, msg.ERROR_EXTRACCION.format(motivo=exc))
                return
            pendiente = Pendiente(
                pendiente_id=f"p-{secrets.token_hex(4)}",
                update_id=update_id,
                telegram_id=telegram_id,
                extraccion=extraccion,
                file_id=file_id,
                mime=mime,
                nota_caption=caption.strip() if caption else None,
                creado=ahora,
                expira=ahora + self.ttl,
            )
            if not extraccion.es_comprobante:
                await self.st.pendientes.guardar(
                    pendiente.model_copy(update={"estado": EstadoPendiente.RECHAZADO})
                )
                await self.tg.enviar(chat_id, msg.NO_COMPROBANTE)
                return
            message_id = await self.tg.enviar(
                chat_id, msg.paso_1(pendiente), kb.paso_compartido(pendiente.pendiente_id)
            )
            await self.st.pendientes.guardar(
                pendiente.model_copy(update={"mensaje_tarjeta_id": message_id})
            )
            log.info("pendiente_creado", pendiente_id=pendiente.pendiente_id)

    async def procesar_texto(
        self, *, update_id: int, telegram_id: int, chat_id: int, texto: str
    ) -> None:
        with bind_context(update_id=update_id, telegram_id=telegram_id):
            persona = await self._persona(telegram_id, chat_id)
            if persona is None:
                return
            p = await self.st.pendientes.esperando_respuesta(telegram_id)
            if p is None or p.vencido(self.reloj()):
                await self.tg.enviar(chat_id, msg.SOLO_FOTOS)  # registro por texto: Fase 3 (R11)
                return
            with bind_context(pendiente_id=p.pendiente_id):
                await self._aplicar_respuesta(p, chat_id, texto)

    async def procesar_callback(
        self, *, telegram_id: int, chat_id: int, message_id: int, data: str
    ) -> str | None:
        """Devuelve el texto del toast (answerCallbackQuery) o None."""
        cb = kb.parsear_callback(data)
        if cb is None:
            return None
        with bind_context(telegram_id=telegram_id, pendiente_id=cb.pendiente_id):
            persona = await self._persona(telegram_id, chat_id)
            if persona is None:
                return None
            p = await self.st.pendientes.obtener(cb.pendiente_id)
            if p is None or p.telegram_id != telegram_id or p.estado is not EstadoPendiente.ABIERTO:
                await self.tg.editar(chat_id, message_id, msg.EXPIRADO)
                return msg.EXPIRADO
            if p.vencido(self.reloj()):
                await self.tg.editar(chat_id, message_id, msg.EXPIRADO)
                return msg.EXPIRADO
            p = p.model_copy(update={"mensaje_tarjeta_id": message_id})
            return await self._accion(cb, p, persona, chat_id)

    # ---------- acciones de la tarjeta ----------

    async def _accion(
        self, cb: kb.Callback, p: Pendiente, persona: Persona, chat_id: int
    ) -> str | None:
        pid = p.pendiente_id
        match cb.accion:
            case kb.Accion.COMPARTIDO:
                p = p.model_copy(update={"compartido": cb.valor == "s"})
                if p.extraccion.moneda_original and p.ediciones.monto is None:
                    await self._pedir(p, chat_id, CampoEsperado.MONTO_USD)
                    return None
                await self._mostrar_resumen(p, chat_id)
            case kb.Accion.DESCARTAR:
                await self.st.pendientes.guardar(
                    p.model_copy(update={"estado": EstadoPendiente.DESCARTADO})
                )
                await self.tg.editar(chat_id, p.mensaje_tarjeta_id or 0, msg.DESCARTADO)
                return msg.DESCARTADO
            case kb.Accion.CATEGORIA:
                catalogo = await self.st.categorias.catalogo()
                await self.st.pendientes.guardar(p)
                await self.tg.editar(
                    chat_id,
                    p.mensaje_tarjeta_id or 0,
                    msg.ELEGIR_CATEGORIA,
                    kb.categorias(pid, catalogo),
                )
            case kb.Accion.ELEGIR_CATEGORIA:
                catalogo = await self.st.categorias.catalogo()
                activas = catalogo.nombres_activos()
                if cb.valor is None or not cb.valor.isdigit() or int(cb.valor) >= len(activas):
                    await self._mostrar_resumen(p, chat_id)
                    return None
                nueva = activas[int(cb.valor)]
                ediciones = p.ediciones.model_copy(
                    update={"subcategoria": None if nueva == p.extraccion.subcategoria else nueva}
                )
                await self._mostrar_resumen(p.model_copy(update={"ediciones": ediciones}), chat_id)
            case kb.Accion.MONEDA:
                await self.st.pendientes.guardar(p)
                await self.tg.editar(
                    chat_id, p.mensaje_tarjeta_id or 0, msg.ELEGIR_MONEDA, kb.monedas(pid)
                )
            case kb.Accion.ELEGIR_MONEDA:
                try:
                    moneda = Moneda(cb.valor or "")
                except ValueError:
                    await self._mostrar_resumen(p, chat_id)
                    return None
                ediciones = p.ediciones.model_copy(update={"moneda": moneda})
                await self._mostrar_resumen(p.model_copy(update={"ediciones": ediciones}), chat_id)
            case kb.Accion.MONTO:
                await self._pedir(p, chat_id, CampoEsperado.MONTO)
            case kb.Accion.FECHA:
                await self._pedir(p, chat_id, CampoEsperado.FECHA)
            case kb.Accion.VOLVER:
                await self._mostrar_resumen(p, chat_id)
            case kb.Accion.GUARDAR:
                if not p.listo_para_guardar:
                    await self._mostrar_resumen(p, chat_id)
                    que = "compartido/personal" if p.compartido is None else "moneda y categoría"
                    return msg.TOAST_FALTA.format(que=que)
                return await self._confirmar(p, persona, chat_id)
        return None

    async def _pedir(self, p: Pendiente, chat_id: int, campo: CampoEsperado) -> None:
        await self.st.pendientes.guardar(p.model_copy(update={"esperando": campo}))
        textos = {
            CampoEsperado.MONTO: msg.PEDIR_MONTO,
            CampoEsperado.FECHA: msg.PEDIR_FECHA,
            CampoEsperado.MONTO_USD: msg.PEDIR_MONTO_USD.format(
                moneda=p.extraccion.moneda_original or "otra moneda"
            ),
        }
        await self.tg.enviar(chat_id, textos[campo], force_reply=True)

    async def _aplicar_respuesta(self, p: Pendiente, chat_id: int, texto: str) -> None:
        try:
            if p.esperando is CampoEsperado.FECHA:
                fecha = parsear_fecha(texto, a_local(self.reloj(), self.zona).date())
                ediciones = p.ediciones.model_copy(update={"fecha": fecha})
            else:
                monto = parsear_monto(texto)
                cambios: dict[str, object] = {"monto": monto}
                if p.esperando is CampoEsperado.MONTO_USD:
                    cambios["moneda"] = Moneda.USD
                ediciones = p.ediciones.model_copy(update=cambios)
        except TextoInvalido:
            invalido = (
                msg.FECHA_INVALIDA if p.esperando is CampoEsperado.FECHA else msg.MONTO_INVALIDO
            )
            await self.tg.enviar(chat_id, invalido, force_reply=True)
            return
        await self._mostrar_resumen(
            p.model_copy(update={"ediciones": ediciones, "esperando": None}), chat_id
        )

    async def _mostrar_resumen(self, p: Pendiente, chat_id: int) -> None:
        """Guarda el pendiente y redibuja la tarjeta en su paso 2."""
        p = p.model_copy(update={"esperando": None})
        catalogo = await self.st.categorias.catalogo()
        rubro = catalogo.buscar(p.subcategoria) if p.subcategoria else None
        texto = msg.resumen(p, rubro.rubro.value if rubro else None)
        teclado = kb.paso_resumen(
            p.pendiente_id, listo=p.listo_para_guardar, moneda_ambigua=p.moneda is None
        )
        if p.mensaje_tarjeta_id is None:
            mid = await self.tg.enviar(chat_id, texto, teclado)
            p = p.model_copy(update={"mensaje_tarjeta_id": mid})
        else:
            await self.tg.editar(chat_id, p.mensaje_tarjeta_id, texto, teclado)
        await self.st.pendientes.guardar(p)

    # ---------- confirmar (R4, R5, R16) ----------

    async def _confirmar(self, p: Pendiente, persona: Persona, chat_id: int) -> str | None:
        assert p.monto is not None and p.moneda is not None and p.subcategoria is not None
        ahora = self.reloj()
        envio_local = a_local(ahora, self.zona)
        mes = mes_de(envio_local.date())
        config = await self.st.config.cargar()
        tc = config.tc_del_mes(mes)
        if tc is None:
            await self.tg.enviar(chat_id, msg.TC_FALTANTE.format(mes=mes))
            return msg.TC_FALTANTE.format(mes=mes)[:200]
        catalogo = await self.st.categorias.catalogo()
        rubro = catalogo.rubro_de(p.subcategoria)
        e = p.extraccion
        reembolso = e.tipo_doc is TipoDocExtraido.REEMBOLSO or p.monto < 0

        subido = None
        try:
            gasto_id = ids.generar_id(envio_local.date(), await self.st.gastos.ids_del_mes(mes))
            if p.file_id:
                contenido = await self.tg.descargar(p.file_id)
                ruta = naming.ruta_carpeta(envio_local.date(), persona.nombre)
                existentes = await self.st.drive.nombres_en(ruta)
                extension = naming.extension_de(p.mime)
                nombre = naming.nombre_disponible(
                    existentes,
                    lambda i: naming.nombre_archivo(
                        envio_local.date(),
                        e.comercio,
                        p.monto or Decimal(0),
                        p.moneda or Moneda.UYU,
                        extension,
                        reembolso=reembolso,
                        intento=i,
                    ),  # fmt: skip
                )
                subido = await self.st.drive.subir(ruta, nombre, contenido, p.mime or "image/jpeg")
            gasto = self._armar_gasto(
                p, persona, gasto_id, envio_local, tc.valor, rubro, subido.link if subido else None
            )
            try:
                await self.st.gastos.agregar(gasto)
            except StorageError:
                if subido is not None:
                    try:
                        await self.st.drive.borrar(subido.file_id)
                    except StorageError:
                        log.error("rollback_drive_fallo", file_id=subido.file_id)
                raise
        except StorageError as exc:
            log.warning("confirmar_fallo", motivo=str(exc))
            await self.tg.enviar(chat_id, msg.ERROR_GUARDAR.format(motivo=exc))
            return msg.ERROR_GUARDAR.format(motivo=exc)[:200]

        await self.st.pendientes.guardar(
            p.model_copy(update={"estado": EstadoPendiente.GUARDADO, "gasto_id": gasto.id})
        )
        dashboard_ok = await self._recalcular_dashboard(mes, config, tc.valor)
        plantilla = msg.GUARDADO if dashboard_ok else msg.GUARDADO_SIN_DASHBOARD
        texto = plantilla.format(
            id=gasto.id,
            resumen=msg.resumen_guardado(p, rubro.value),
            link=gasto.link_imagen or "sin imagen",
        )
        await self.tg.editar(chat_id, p.mensaje_tarjeta_id or 0, texto)
        log.info("gasto_guardado", gasto_id=gasto.id, mes=mes)
        return msg.TOAST_OK

    def _armar_gasto(
        self,
        p: Pendiente,
        persona: Persona,
        gasto_id: str,
        envio_local: datetime,
        tc: Decimal,
        rubro: Rubro,
        link: str | None,
    ) -> Gasto:
        e = p.extraccion
        assert p.monto is not None and p.moneda is not None and p.subcategoria is not None
        notas = [x for x in (e.cuota, p.nota_caption) if x]
        if e.moneda_original:
            notas.append(f"original: {e.monto_original or '?'} {e.moneda_original}")
        tipo_doc = TipoDoc.TEXTO if p.origen is TipoDoc.TEXTO else TipoDoc(e.tipo_doc.value)
        return Gasto(
            id=gasto_id,
            fecha_gasto=p.fecha or envio_local.date(),
            fecha_envio=envio_local,
            quien_subio=persona.nombre,
            compartido=bool(p.compartido),
            comercio=e.comercio or "",
            monto=p.monto,
            moneda=p.moneda,
            tc_mes=tc,
            monto_usd=a_usd(p.monto, p.moneda, tc),
            rubro=rubro,
            subcategoria=p.subcategoria,
            medio_pago=f"tarjeta …{e.ultimos4_tarjeta}" if e.ultimos4_tarjeta else None,
            tipo_doc=tipo_doc,
            nota=" · ".join(notas) or None,
            quincena=quincena_de(envio_local.date()),
            editado=p.ediciones.hubo,
            link_imagen=link,
        )

    async def _recalcular_dashboard(self, mes: str, config: object, tc: Decimal) -> bool:
        from gastos_bot.domain.models import Config

        assert isinstance(config, Config)
        try:
            gastos = await self.st.gastos.listar_mes(mes)
            primer_dia = datetime.strptime(mes, "%Y-%m").date()
            indicador = calcular(
                mes,
                gastos,
                ingreso_usd=ingreso_conjunto_usd(config, primer_dia, tc),
                tc_uyu_usd=tc,
                porcentajes=config.porcentajes,
                personas=[per.nombre for per in config.personas],
            )
            await self.st.dashboard.recalcular(indicador)
            return True
        except StorageError as exc:
            log.warning("dashboard_fallo", motivo=str(exc))
            return False

    # ---------- helpers ----------

    async def _persona(self, telegram_id: int, chat_id: int) -> Persona | None:
        try:
            config = await self.st.config.cargar()
        except StorageError as exc:
            await self.tg.enviar(chat_id, msg.ERROR_GUARDAR.format(motivo=exc))
            return None
        persona = config.persona_por_id(telegram_id)
        if persona is None:
            log.warning("persona_no_configurada")
            await self.tg.enviar(chat_id, msg.SIN_CONFIG)
        return persona
