"""Modelos del dominio (PRD §7 R2, §9). Puros: sin I/O, sin imports de otras capas.

Dos vocabularios de ``tipo_doc`` a propósito: el LLM devuelve ``otro`` cuando la imagen no es un
comprobante (y no se crea pendiente); la fila del Sheet guarda ``texto`` para registros sin foto
(R11). Nunca se guarda ``otro`` y el LLM nunca devuelve ``texto``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gastos_bot.domain.categorias import Rubro


class Moneda(StrEnum):
    UYU = "UYU"
    USD = "USD"


class MonedaExtraida(StrEnum):
    """Lo que puede decir el LLM. ``ambigua`` bloquea Guardar hasta que el usuario elija (R3)."""

    UYU = "UYU"
    USD = "USD"
    AMBIGUA = "ambigua"


class TipoDocExtraido(StrEnum):
    FACTURA = "factura"
    DEBITO = "debito"
    REEMBOLSO = "reembolso"
    OTRO = "otro"


class TipoDoc(StrEnum):
    FACTURA = "factura"
    DEBITO = "debito"
    REEMBOLSO = "reembolso"
    TEXTO = "texto"


class Quincena(StrEnum):
    Q1 = "Q1"  # 1–15
    Q2 = "Q2"  # 16–fin


class Estado(StrEnum):
    ACTIVO = "activo"
    ELIMINADO = "eliminado"


class EstadoPendiente(StrEnum):
    """Ciclo de vida de un pendiente. Se guarda dentro de ``json_extraccion`` (ADR 0003)."""

    ABIERTO = "abierto"
    GUARDADO = "guardado"
    DESCARTADO = "descartado"
    RECHAZADO = "rechazado"  # la imagen no era un comprobante (tipo_doc = otro)


class CampoEsperado(StrEnum):
    """Qué respuesta de texto (ForceReply) está esperando la tarjeta (R3)."""

    MONTO = "monto"
    FECHA = "fecha"
    MONTO_USD = "monto_usd"  # D3: moneda extranjera


Monto = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]
Confianza01 = Annotated[float, Field(ge=0.0, le=1.0)]


class Persona(BaseModel):
    model_config = ConfigDict(frozen=True)

    nombre: str = Field(min_length=1)
    telegram_id: int


class Confianza(BaseModel):
    """Confianza por campo (R2). 0 = el modelo no lo vio; 1 = seguro."""

    model_config = ConfigDict(frozen=True)

    monto: Confianza01 = 0.0
    moneda: Confianza01 = 0.0
    fecha: Confianza01 = 0.0
    comercio: Confianza01 = 0.0
    subcategoria: Confianza01 = 0.0


class Extraccion(BaseModel):
    """Salida validada del LLM (R2). Todo opcional salvo ``tipo_doc``: el modelo no inventa."""

    model_config = ConfigDict(frozen=True)

    tipo_doc: TipoDocExtraido
    monto: Monto | None = None  # negativo si reembolso (D2)
    moneda: MonedaExtraida | None = None
    fecha: date | None = None
    comercio: str | None = None
    ultimos4_tarjeta: Annotated[str, Field(pattern=r"^\d{4}$")] | None = None
    cuota: str | None = None  # "cuota 3/12" tal como aparece (D1)
    subcategoria: str | None = None  # siempre de la lista viva de Categorias (R6)
    moneda_original: str | None = None  # D3: si no es UYU/USD
    monto_original: Monto | None = None
    confianza: Confianza = Confianza()

    @field_validator("comercio", "cuota", "subcategoria", "moneda_original", mode="before")
    @classmethod
    def _vacio_es_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v.strip() if isinstance(v, str) else v

    @property
    def es_comprobante(self) -> bool:
        return self.tipo_doc is not TipoDocExtraido.OTRO

    @property
    def moneda_ambigua(self) -> bool:
        return self.moneda is None or self.moneda is MonedaExtraida.AMBIGUA


class Ediciones(BaseModel):
    """Correcciones del usuario sobre la extracción, campo a campo (R3). None = sin tocar."""

    model_config = ConfigDict(frozen=True)

    monto: Monto | None = None
    moneda: Moneda | None = None
    fecha: date | None = None
    subcategoria: str | None = None

    @property
    def hubo(self) -> bool:
        return any(v is not None for v in (self.monto, self.moneda, self.fecha, self.subcategoria))


class Pendiente(BaseModel):
    """Gasto extraído a la espera de confirmación (D5). Vive en la pestaña Pendientes."""

    model_config = ConfigDict(frozen=True)

    pendiente_id: str = Field(min_length=1)
    update_id: int
    telegram_id: int
    extraccion: Extraccion
    file_id: str | None = None  # file_id de Telegram; None si vino por texto (R11)
    origen: TipoDoc | None = None  # TEXTO cuando no hay comprobante
    compartido: bool | None = None  # paso 1 obligatorio de la tarjeta (R3)
    ediciones: Ediciones = Ediciones()
    nota_caption: str | None = None
    mime: str | None = None
    creado: datetime
    expira: datetime
    estado: EstadoPendiente = EstadoPendiente.ABIERTO
    esperando: CampoEsperado | None = None
    mensaje_tarjeta_id: int | None = None  # message_id de la tarjeta, para editarla
    gasto_id: str | None = None  # se completa al guardar; en /editar apunta a la fila a reescribir
    repetido_de: str | None = None  # ID del gasto que se está repitiendo (R23)

    # Valores efectivos = extracción con las ediciones encima.
    @property
    def monto(self) -> Decimal | None:
        return self.ediciones.monto if self.ediciones.monto is not None else self.extraccion.monto

    @property
    def moneda(self) -> Moneda | None:
        if self.ediciones.moneda is not None:
            return self.ediciones.moneda
        if self.extraccion.moneda in (MonedaExtraida.UYU, MonedaExtraida.USD):
            return Moneda(self.extraccion.moneda.value)
        return None

    @property
    def fecha(self) -> date | None:
        return self.ediciones.fecha or self.extraccion.fecha

    @property
    def subcategoria(self) -> str | None:
        return self.ediciones.subcategoria or self.extraccion.subcategoria

    @property
    def listo_para_guardar(self) -> bool:
        """Guardar se habilita solo con compartido/personal resuelto, moneda y monto (R3)."""
        return (
            self.compartido is not None
            and self.moneda is not None
            and self.monto is not None
            and self.subcategoria is not None
        )

    def vencido(self, ahora: datetime) -> bool:
        return ahora >= self.expira


class Gasto(BaseModel):
    """Una fila de la pestaña del mes (PRD §9). Orden de campos = orden de columnas."""

    model_config = ConfigDict(frozen=True)

    id: Annotated[str, Field(pattern=r"^G-\d{6}-\d{3,}$")]
    fecha_gasto: date
    fecha_envio: datetime
    quien_subio: str
    compartido: bool
    comercio: str
    monto: Monto
    moneda: Moneda
    tc_mes: Annotated[Decimal, Field(gt=0)]
    monto_usd: Monto
    rubro: Rubro
    subcategoria: str
    medio_pago: str | None = None
    tipo_doc: TipoDoc
    nota: str | None = None
    quincena: Quincena
    editado: bool
    link_imagen: str | None = None
    estado: Estado = Estado.ACTIVO
    fecha_modificacion: datetime | None = None


class Ingreso(BaseModel):
    model_config = ConfigDict(frozen=True)

    nombre: str
    monto: Monto
    moneda: Moneda
    vigente_desde: date


class TipoCambio(BaseModel):
    """UYU por USD fijado para un mes (R7)."""

    model_config = ConfigDict(frozen=True)

    mes: Annotated[str, Field(pattern=r"^\d{4}-\d{2}$")]
    valor: Annotated[Decimal, Field(gt=0)]
    fecha: date | None = None


class Porcentajes(BaseModel):
    model_config = ConfigDict(frozen=True)

    necesidades: Annotated[int, Field(ge=0, le=100)] = 50
    deseos: Annotated[int, Field(ge=0, le=100)] = 30
    ahorro: Annotated[int, Field(ge=0, le=100)] = 20

    @model_validator(mode="after")
    def _suman_100(self) -> Porcentajes:
        total = self.necesidades + self.deseos + self.ahorro
        if total != 100:
            raise ValueError(f"los porcentajes tienen que sumar 100, suman {total}")
        return self


class Config(BaseModel):
    """Contenido de la pestaña Config ya interpretado (ADR 0002)."""

    model_config = ConfigDict(frozen=True)

    personas: tuple[Persona, ...]
    ingresos: tuple[Ingreso, ...] = ()
    tipos_de_cambio: tuple[TipoCambio, ...] = ()
    zona_horaria: str = "America/Montevideo"
    hora_reporte: str = "09:00"
    porcentajes: Porcentajes = Porcentajes()
    carpetas: dict[str, str] = Field(default_factory=dict)  # ruta relativa → folder id

    def persona_por_id(self, telegram_id: int) -> Persona | None:
        return next((p for p in self.personas if p.telegram_id == telegram_id), None)

    def ingreso_vigente(self, nombre: str, mes: date) -> Ingreso | None:
        """El ingreso con ``vigente_desde`` más reciente que no sea posterior al mes (D8)."""
        candidatos = [i for i in self.ingresos if i.nombre == nombre and i.vigente_desde <= mes]
        return max(candidatos, key=lambda i: i.vigente_desde, default=None)

    def tc_del_mes(self, mes: str) -> TipoCambio | None:
        return next((tc for tc in self.tipos_de_cambio if tc.mes == mes), None)
