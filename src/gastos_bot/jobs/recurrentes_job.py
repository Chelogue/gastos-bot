"""Materializa las recurrencias vencidas y avisa por Telegram a quien las creó."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gastos_bot.bot import keyboards as kb
from gastos_bot.bot import messages as msg
from gastos_bot.domain import ids
from gastos_bot.domain.fx import a_usd
from gastos_bot.domain.models import Gasto, Recurrencia, TipoDoc
from gastos_bot.domain.quincena import mes_de, quincena_de
from gastos_bot.domain.recurrentes import sumar_periodo
from gastos_bot.jobs.base import Avisador, Resultado, avisar
from gastos_bot.logging_setup import get_logger
from gastos_bot.storage.base import StorageError
from gastos_bot.storage.dashboard import recalcular_mes
from gastos_bot.storage.factory import Storage

log = get_logger("gastos_bot.jobs.recurrentes")


async def ejecutar(*, storage: Storage, avisador: Avisador, ahora: datetime) -> Resultado:
    config = await storage.config.cargar()
    creados = 0
    omitidos = 0
    fallidos = 0
    avisados: list[int] = []
    meses_afectados: set[str] = set()

    for original in await storage.recurrentes.listar_activas():
        recurrencia = original
        while recurrencia.proxima_fecha <= ahora.date():
            vencimiento = recurrencia.proxima_fecha
            mes = mes_de(vencimiento)
            tc = config.tc_del_mes(mes)
            if tc is None:
                fallidos += 1
                enviados = await avisar(
                    avisador,
                    (recurrencia.telegram_id,),
                    msg.RECURRENCIA_SIN_TC.format(
                        id=recurrencia.id, mes=mes, comercio=recurrencia.comercio
                    ),
                )
                avisados.extend(enviados)
                break
            try:
                existentes = await storage.gastos.listar_mes(mes)
                gasto = next(
                    (
                        g
                        for g in existentes
                        if g.recurrente_id == recurrencia.id and g.fecha_gasto == vencimiento
                    ),
                    None,
                )
                if gasto is None:
                    gasto = await _crear_gasto(storage, recurrencia, ahora, tc.valor)
                    await storage.gastos.agregar(gasto)
                    creados += 1
                    meses_afectados.add(mes)
                else:
                    omitidos += 1
                siguiente = sumar_periodo(vencimiento, recurrencia.frecuencia, recurrencia.dia_mes)
                recurrencia = recurrencia.model_copy(
                    update={
                        "proxima_fecha": siguiente,
                        "ultimo_gasto_id": gasto.id,
                        "fecha_modificacion": ahora,
                    }
                )
                await storage.recurrentes.guardar(recurrencia)
                enviados = await avisar(
                    avisador,
                    (recurrencia.telegram_id,),
                    msg.gasto_recurrente_registrado(gasto, recurrencia.id),
                    kb.seguimiento_recurrencia(recurrencia.id),
                )
                avisados.extend(enviados)
            except StorageError as exc:
                fallidos += 1
                log.warning("recurrencia_fallida", recurrente_id=recurrencia.id, motivo=str(exc))
                break

    for mes in sorted(meses_afectados):
        tc = config.tc_del_mes(mes)
        if tc is None:
            continue
        try:
            await recalcular_mes(storage.gastos, storage.dashboard, mes, config, tc.valor)
        except StorageError as exc:
            log.warning("dashboard_recurrentes_fallo", mes=mes, motivo=str(exc))

    return Resultado(
        "recurrentes",
        fallidos == 0,
        {"creados": creados, "omitidos": omitidos, "fallidos": fallidos},
        tuple(avisados),
    )


async def _crear_gasto(
    storage: Storage, recurrencia: Recurrencia, ahora: datetime, tc: Decimal
) -> Gasto:
    fecha = recurrencia.proxima_fecha
    mes = mes_de(fecha)
    gasto_id = ids.generar_id(fecha, await storage.gastos.ids_del_mes(mes))
    envio = datetime.combine(fecha, ahora.timetz())
    return Gasto(
        id=gasto_id,
        fecha_gasto=fecha,
        fecha_envio=envio,
        quien_subio=recurrencia.quien_subio,
        compartido=recurrencia.compartido,
        comercio=recurrencia.comercio,
        monto=recurrencia.monto,
        moneda=recurrencia.moneda,
        tc_mes=tc,
        monto_usd=a_usd(recurrencia.monto, recurrencia.moneda, tc),
        rubro=recurrencia.rubro,
        subcategoria=recurrencia.subcategoria,
        medio_pago=recurrencia.medio_pago,
        tipo_doc=TipoDoc.TEXTO,
        nota=recurrencia.nota,
        quincena=quincena_de(fecha),
        editado=False,
        recurrente_id=recurrencia.id,
    )
