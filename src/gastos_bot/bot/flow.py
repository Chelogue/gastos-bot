"""Orquestación foto → extracción → pendiente → tarjeta → confirmar → Drive → Sheets → Dashboard.

Único lugar que conecta las capas. No conoce a python-telegram-bot: habla con Telegram a través
de ``Mensajero`` (que ``app.py`` implementa) y con Google a través de ``Storage``. Así se testea
entero con dobles (tests/unit/test_flow.py).
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from gastos_bot.bot import keyboards as kb
from gastos_bot.bot import messages as msg
from gastos_bot.domain import ids, naming
from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.consultas import es_consulta_total, es_consulta_ultimos, periodo_pedido
from gastos_bot.domain.duplicados import buscar_duplicado
from gastos_bot.domain.fx import a_usd
from gastos_bot.domain.ids import mes_de_id
from gastos_bot.domain.models import (
    CampoEsperado,
    Estado,
    EstadoPendiente,
    Extraccion,
    Gasto,
    Moneda,
    MonedaExtraida,
    Pendiente,
    Persona,
    TipoDoc,
    TipoDocExtraido,
)
from gastos_bot.domain.parseo import TextoInvalido, parsear_fecha, parsear_monto
from gastos_bot.domain.quincena import a_local, mes_anterior, mes_de, quincena_de
from gastos_bot.extraction.base import Entrada, ExtraccionFallida, Extractor
from gastos_bot.logging_setup import bind_context, get_logger
from gastos_bot.reports import quincenal
from gastos_bot.storage.base import StorageError
from gastos_bot.storage.dashboard import recalcular_mes
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


def _activos(gastos: list[Gasto]) -> list[Gasto]:
    return [g for g in gastos if g.estado is Estado.ACTIVO]


def _como_extraccion(gasto: Gasto) -> Extraccion:
    """Un gasto guardado visto como extracción, para reusar la tarjeta al editar (R13)."""
    try:
        tipo = TipoDocExtraido(gasto.tipo_doc.value)
    except ValueError:  # tipo_doc = texto no existe del lado del LLM
        tipo = TipoDocExtraido.OTRO
    return Extraccion(
        tipo_doc=tipo,
        monto=gasto.monto,
        moneda=MonedaExtraida(gasto.moneda.value),
        fecha=gasto.fecha_gasto,
        comercio=gasto.comercio or None,
        subcategoria=gasto.subcategoria,
    )


class Flujo:
    def __init__(
        self,
        *,
        extractor: Extractor,
        storage: Storage,
        mensajero: Mensajero,
        zona: str = "America/Montevideo",
        ttl_horas: int = 48,
        sheet_id: str | None = None,
        reloj: Callable[[], datetime] = _ahora_utc,
    ) -> None:
        self.extractor = extractor
        self.st = storage
        self.tg = mensajero
        self.zona = zona
        self.ttl = timedelta(hours=ttl_horas)
        self.sheet_id = sheet_id
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
            await self._abrir_tarjeta(pendiente, chat_id, msg.NO_COMPROBANTE)

    async def procesar_texto(
        self, *, update_id: int, telegram_id: int, chat_id: int, texto: str
    ) -> None:
        with bind_context(update_id=update_id, telegram_id=telegram_id):
            persona = await self._persona(telegram_id, chat_id)
            if persona is None:
                return
            p = await self.st.pendientes.esperando_respuesta(telegram_id)
            if p is not None and not p.vencido(self.reloj()):
                with bind_context(pendiente_id=p.pendiente_id):
                    await self._aplicar_respuesta(p, chat_id, texto)
                return
            if es_consulta_total(texto):  # «cuánto llevamos» (R12)
                await self.total(telegram_id=telegram_id, chat_id=chat_id)
                return
            if es_consulta_ultimos(texto):
                await self.ultimos(telegram_id=telegram_id, chat_id=chat_id)
                return
            await self._registrar_texto(
                update_id=update_id, telegram_id=telegram_id, chat_id=chat_id, texto=texto
            )

    async def _registrar_texto(
        self, *, update_id: int, telegram_id: int, chat_id: int, texto: str
    ) -> None:
        """Un gasto escrito a mano: «450 uyu farmacia» (R11). Misma tarjeta, sin imagen."""
        if await self.st.pendientes.update_visto(update_id):
            log.info("update_duplicado")
            return
        ahora = self.reloj()
        try:
            catalogo = await self.st.categorias.catalogo()
            extraccion = await self.extractor.extraer(
                Entrada(texto=texto), catalogo.nombres_activos()
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
            origen=TipoDoc.TEXTO,
            nota_caption=None,
            creado=ahora,
            expira=ahora + self.ttl,
        )
        await self._abrir_tarjeta(pendiente, chat_id, msg.NO_ENTENDI_TEXTO)

    async def _abrir_tarjeta(self, pendiente: Pendiente, chat_id: int, rechazo: str) -> None:
        """Paso 1 de la tarjeta, o el mensaje de rechazo si no es un gasto."""
        if not pendiente.extraccion.es_comprobante:
            await self.st.pendientes.guardar(
                pendiente.model_copy(update={"estado": EstadoPendiente.RECHAZADO})
            )
            await self.tg.enviar(chat_id, rechazo)
            return
        message_id = await self.tg.enviar(
            chat_id, msg.paso_1(pendiente), kb.paso_compartido(pendiente.pendiente_id)
        )
        await self.st.pendientes.guardar(
            pendiente.model_copy(update={"mensaje_tarjeta_id": message_id})
        )
        log.info("pendiente_creado", pendiente_id=pendiente.pendiente_id, origen=pendiente.origen)

    # ---------- consultas (R12) ----------

    async def total(self, *, telegram_id: int, chat_id: int) -> None:
        """Cómo viene la quincena en curso: mismo cálculo que el reporte quincenal."""
        await self.reporte(telegram_id=telegram_id, chat_id=chat_id)

    async def reporte(self, *, telegram_id: int, chat_id: int, cual: str | None = None) -> None:
        """``/reporte`` a demanda (R22): quincena en curso, la anterior o el mes entero."""
        with bind_context(telegram_id=telegram_id):
            if await self._persona(telegram_id, chat_id) is None:
                return
            hoy = a_local(self.reloj(), self.zona).date()
            periodo = periodo_pedido(cual, hoy)
            mes = periodo.mes.mes
            try:
                config = await self.st.config.cargar()
                tc = config.tc_del_mes(mes)
                if tc is None:
                    await self.tg.enviar(chat_id, msg.SIN_TC_CONSULTA.format(mes=mes))
                    return
                gastos = await self.st.gastos.listar_mes(mes)
            except StorageError as exc:
                await self.tg.enviar(chat_id, msg.ERROR_GUARDAR.format(motivo=exc))
                return
            reporte = quincenal.armar(
                periodo=periodo,
                gastos_del_mes=gastos,
                config=config,
                tc=tc.valor,
                hoy=hoy,
                sheet_id=self.sheet_id,
                folder_id=config.carpetas.get(mes),
            )
            await self.tg.enviar(chat_id, msg.reporte(reporte))

    async def ultimos(self, *, telegram_id: int, chat_id: int, cuantos: int = 10) -> None:
        """Los últimos movimientos con su ID, para poder editarlos o borrarlos."""
        with bind_context(telegram_id=telegram_id):
            if await self._persona(telegram_id, chat_id) is None:
                return
            hoy = a_local(self.reloj(), self.zona).date()
            try:
                gastos = _activos(await self.st.gastos.listar_mes(mes_de(hoy)))
                if len(gastos) < cuantos:  # arrancando el mes, se mira también el anterior
                    previos = _activos(await self.st.gastos.listar_mes(mes_de(mes_anterior(hoy))))
                    gastos = previos + gastos
            except StorageError as exc:
                await self.tg.enviar(chat_id, msg.ERROR_GUARDAR.format(motivo=exc))
                return
            await self.tg.enviar(chat_id, msg.ultimos(gastos[-cuantos:]))

    # ---------- corregir y borrar (R13) ----------

    async def borrar(self, *, telegram_id: int, chat_id: int, gasto_id: str) -> None:
        """Pide confirmación; borrar de verdad pasa por el botón (R13)."""
        with bind_context(telegram_id=telegram_id, gasto_id=gasto_id):
            if await self._persona(telegram_id, chat_id) is None:
                return
            gasto = await self._buscar_gasto(gasto_id, chat_id)
            if gasto is None:
                return
            if gasto.estado is Estado.ELIMINADO:
                await self.tg.enviar(chat_id, msg.GASTO_YA_BORRADO.format(id=gasto.id))
                return
            await self.tg.enviar(
                chat_id,
                msg.BORRAR_CONFIRMAR.format(resumen=msg.gasto_linea(gasto)),
                kb.confirmar_borrado(gasto.id),
            )

    async def editar(
        self, *, update_id: int, telegram_id: int, chat_id: int, gasto_id: str
    ) -> None:
        """Abre la misma tarjeta del alta, pero apuntando a una fila que ya existe (R13)."""
        with bind_context(telegram_id=telegram_id, gasto_id=gasto_id):
            if await self._persona(telegram_id, chat_id) is None:
                return
            gasto = await self._buscar_gasto(gasto_id, chat_id)
            if gasto is None:
                return
            if gasto.estado is Estado.ELIMINADO:
                await self.tg.enviar(chat_id, msg.GASTO_YA_BORRADO.format(id=gasto.id))
                return
            ahora = self.reloj()
            pendiente = Pendiente(
                pendiente_id=f"e-{secrets.token_hex(4)}",
                update_id=update_id,
                telegram_id=telegram_id,
                extraccion=_como_extraccion(gasto),
                origen=gasto.tipo_doc,
                compartido=gasto.compartido,
                gasto_id=gasto.id,
                creado=ahora,
                expira=ahora + self.ttl,
            )
            await self._mostrar_resumen(pendiente, chat_id)

    async def _guardar_edicion(self, p: Pendiente, chat_id: int) -> str | None:
        """Reescribe la fila del gasto con lo que quedó en la tarjeta (R13)."""
        assert p.gasto_id and p.monto is not None and p.moneda is not None
        assert p.subcategoria is not None
        original = await self._buscar_gasto(p.gasto_id, chat_id)
        if original is None:
            return None
        mes = mes_de_id(original.id) or mes_de(original.fecha_envio.date())
        config = await self.st.config.cargar()
        tc = config.tc_del_mes(mes)
        if tc is None:
            await self.tg.enviar(chat_id, msg.TC_FALTANTE.format(mes=mes))
            return msg.TC_FALTANTE.format(mes=mes)[:200]
        catalogo = await self.st.categorias.catalogo()
        rubro = catalogo.rubro_de(p.subcategoria)
        actualizado = original.model_copy(
            update={
                "fecha_gasto": p.fecha or original.fecha_gasto,
                "compartido": bool(p.compartido),
                "monto": p.monto,
                "moneda": p.moneda,
                "tc_mes": tc.valor,
                "monto_usd": a_usd(p.monto, p.moneda, tc.valor),
                "rubro": rubro,
                "subcategoria": p.subcategoria,
                "editado": True,
                "fecha_modificacion": a_local(self.reloj(), self.zona),
            }
        )
        try:
            if not await self.st.gastos.actualizar(actualizado):
                await self.tg.enviar(chat_id, msg.GASTO_NO_ENCONTRADO.format(id=actualizado.id))
                return None
        except StorageError as exc:
            log.warning("edicion_fallida", motivo=str(exc))
            await self.tg.enviar(chat_id, msg.ERROR_GUARDAR.format(motivo=exc))
            return msg.ERROR_GUARDAR.format(motivo=exc)[:200]
        await self.st.pendientes.guardar(p.model_copy(update={"estado": EstadoPendiente.GUARDADO}))
        log.info("gasto_editado", gasto_id=actualizado.id, mes=mes)
        await self.tg.editar(
            chat_id,
            p.mensaje_tarjeta_id or 0,
            msg.EDITADO.format(id=actualizado.id, resumen=msg.gasto_linea(actualizado)),
        )
        await self._recalcular_dashboard(mes, config, tc.valor)
        return msg.TOAST_OK

    async def _buscar_gasto(self, gasto_id: str, chat_id: int) -> Gasto | None:
        limpio = gasto_id.strip().upper()
        try:
            gasto = await self.st.gastos.obtener(limpio)
        except StorageError as exc:
            await self.tg.enviar(chat_id, msg.ERROR_GUARDAR.format(motivo=exc))
            return None
        if gasto is None:
            await self.tg.enviar(chat_id, msg.GASTO_NO_ENCONTRADO.format(id=limpio))
        return gasto

    async def _resolver_borrado(self, cb: kb.Callback, chat_id: int, message_id: int) -> str | None:
        gasto_id = cb.pendiente_id
        if cb.accion is kb.Accion.BORRAR_NO:
            await self.tg.editar(chat_id, message_id, msg.BORRAR_CANCELADO)
            return msg.BORRAR_CANCELADO
        gasto = await self._buscar_gasto(gasto_id, chat_id)
        if gasto is None:
            return None
        if gasto.estado is Estado.ELIMINADO:
            await self.tg.editar(chat_id, message_id, msg.GASTO_YA_BORRADO.format(id=gasto.id))
            return None
        ahora_local = a_local(self.reloj(), self.zona)
        try:
            await self.st.gastos.actualizar(
                gasto.model_copy(
                    update={"estado": Estado.ELIMINADO, "fecha_modificacion": ahora_local}
                )
            )
        except StorageError as exc:
            await self.tg.enviar(chat_id, msg.ERROR_GUARDAR.format(motivo=exc))
            return None
        log.info("gasto_borrado", gasto_id=gasto.id)
        await self.tg.editar(chat_id, message_id, msg.BORRADO.format(id=gasto.id))
        await self._recalcular_del_gasto(gasto.id)
        return msg.TOAST_OK

    async def _recalcular_del_gasto(self, gasto_id: str) -> None:
        """Deja el Dashboard al día después de editar o borrar una fila (R10, R13)."""
        mes = mes_de_id(gasto_id)
        if mes is None:
            return
        try:
            config = await self.st.config.cargar()
        except StorageError:
            return
        tc = config.tc_del_mes(mes)
        if tc is not None:
            await self._recalcular_dashboard(mes, config, tc.valor)

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
            if cb.accion in (kb.Accion.BORRAR_SI, kb.Accion.BORRAR_NO):
                return await self._resolver_borrado(cb, chat_id, message_id)
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
            case kb.Accion.GUARDAR_IGUAL:
                if not p.listo_para_guardar:
                    await self._mostrar_resumen(p, chat_id)
                    return None
                return await self._confirmar(p, persona, chat_id, forzar=True)
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

    async def _confirmar(
        self, p: Pendiente, persona: Persona, chat_id: int, forzar: bool = False
    ) -> str | None:
        assert p.monto is not None and p.moneda is not None and p.subcategoria is not None
        if p.gasto_id:  # la tarjeta salió de /editar: no hay alta ni subida a Drive (R13)
            return await self._guardar_edicion(p, chat_id)
        ahora = self.reloj()
        envio_local = a_local(ahora, self.zona)
        mes = mes_de(envio_local.date())
        config = await self.st.config.cargar()
        tc = config.tc_del_mes(mes)
        if tc is None:
            await self.tg.enviar(chat_id, msg.TC_FALTANTE.format(mes=mes))
            return msg.TC_FALTANTE.format(mes=mes)[:200]
        if not forzar and (duplicado := await self._duplicado_de(p, mes, envio_local.date())):
            log.info("posible_duplicado", gasto_id=duplicado.id)
            await self.st.pendientes.guardar(p)
            await self.tg.editar(
                chat_id,
                p.mensaje_tarjeta_id or 0,
                msg.POSIBLE_DUPLICADO.format(resumen=msg.gasto_linea(duplicado)),
                kb.confirmar_duplicado(p.pendiente_id),
            )
            return msg.TOAST_DUPLICADO
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
                        persona=persona.nombre,
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

    async def _duplicado_de(self, p: Pendiente, mes: str, hoy: date) -> Gasto | None:
        """Busca un gasto parecido ya guardado (R20). Si Sheets falla, no bloquea el alta."""
        assert p.monto is not None and p.moneda is not None
        try:
            del_mes = await self.st.gastos.listar_mes(mes)
        except StorageError:
            return None
        return buscar_duplicado(
            fecha=p.fecha or hoy,
            monto=p.monto,
            moneda=p.moneda,
            comercio=p.extraccion.comercio,
            gastos=del_mes,
        )

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
            await recalcular_mes(self.st.gastos, self.st.dashboard, mes, config, tc)
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
