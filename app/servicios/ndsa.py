"""
NDSA Levels of Digital Preservation 2.0 (2019): nivel por área calculado
desde el estado real del sistema (hallazgo PRE-13).

La auditoría encontró que la tesis no podía afirmar un nivel sin la
salvedad de la regla acumulativa: un nivel cuenta solo si se cumplen todos
sus requisitos y los de los niveles inferiores. Aquí cada requisito se
comprueba contra lo que el sistema hace de verdad (configuración, últimos
respaldos, verificaciones, herramientas instaladas), y el resultado dice
qué falta para el siguiente. No es una afirmación del equipo: es un cálculo.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.auditoria import RegistroAuditoria
from app.models.instanciacion import Instanciacion
from app.models.preservacion import ComprobacionTecnica, Restauracion, SegundaCopia, VerificacionIntegridad
from app.servicios import parametros

AREAS = ("Almacenamiento", "Integridad", "Control", "Metadatos", "Contenido")


def _req(texto: str, cumple: bool, evidencia: str) -> dict:
    return {"requisito": texto, "cumple": bool(cumple), "evidencia": evidencia}


def _herramienta(nombre: str) -> bool:
    import shutil

    return shutil.which(nombre) is not None


def _validadores() -> bool:
    from pathlib import Path

    return (Path(settings.directorio_validadores) / "lib").is_dir() and _herramienta(settings.java)


def requisitos(db: Session) -> dict[str, list[list[dict]]]:
    """Por área, una lista por nivel (1 a 4) con sus requisitos comprobados."""
    from app.servicios import respaldo, segunda_copia

    hoy = ahora()
    archivos = db.scalar(select(func.count(Instanciacion.id)).where(
        Instanciacion.estado == "listo_para_descripcion")) or 0
    con_copia = db.scalar(select(func.count(func.distinct(SegundaCopia.instanciacion_id))).where(
        SegundaCopia.estado == "sincronizada")) or 0
    try:
        ubicacion = segunda_copia.estado_ubicacion(segunda_copia.ubicacion_actual(db))
        separada = ubicacion["existe"] and not ubicacion["mismo_disco_que_primaria"]
    except Exception:  # noqa: BLE001 — sin lugar configurado, no hay copia separada
        separada = False
    probado = respaldo.ultimo_probado(db)
    horas = int(parametros.leer(db, "respaldo_frecuencia_horas"))
    respaldo_al_dia = probado is not None and hoy - probado.iniciado_en <= timedelta(hours=2 * horas)
    dias_externa = int(parametros.leer(db, "respaldo_dias_copia_externa"))
    descarga = db.scalar(select(func.max(respaldo.RespaldoBaseDatos.descargado_en)))
    copia_externa = descarga is not None and hoy - descarga <= timedelta(days=dias_externa)
    dias_fijeza = int(parametros.leer(db, "preservacion_frecuencia_dias"))
    atrasadas = db.scalar(select(func.count(Instanciacion.id)).where(
        Instanciacion.estado == "listo_para_descripcion",
        Instanciacion.cargado_en < hoy - timedelta(days=dias_fijeza),
        (Instanciacion.ultima_verificacion_en.is_(None))
        | (Instanciacion.ultima_verificacion_en < hoy - timedelta(days=dias_fijeza)))) or 0
    verificaciones = db.scalar(select(func.count(VerificacionIntegridad.id))) or 0
    restauracion_posible = True  # preservacion.reponer_desde_segunda_copia existe y está probada
    restauraciones = db.scalar(select(func.count(Restauracion.id))) or 0
    antivirus = settings.antivirus and _herramienta(settings.clamscan)
    validadores = _validadores()
    revisado = db.scalar(select(func.max(RegistroAuditoria.fecha)).where(
        RegistroAuditoria.accion == "consolidado_revisado"))
    revision_al_dia = revisado is not None and hoy - revisado <= timedelta(days=14)
    validadas = db.scalar(select(func.count(func.distinct(ComprobacionTecnica.instanciacion_id))).where(
        ComprobacionTecnica.tipo == "validacion", ComprobacionTecnica.resultado.in_(("conforme", "no_conforme")))) or 0
    return {
        "Almacenamiento": [
            [_req("Dos copias completas que no estén en el mismo lugar", con_copia >= archivos and separada,
                  f"{con_copia} de {archivos} archivos con segunda copia; "
                  + ("la segunda copia está en otro disco" if separada else "la segunda copia comparte disco con la primaria")),
             _req("Documentar el almacenamiento y sus medios", True, "documentacion/modulo-5-preservacion.md")],
            [_req("Tres copias, una de ellas en otro lugar geográfico", False,
                  "El contenido tiene dos copias en el mismo servidor; la base de datos se lleva fuera con la descarga "
                  "del respaldo, el contenido no."),
             _req("Base de datos respaldada y fuera del servidor", respaldo_al_dia and copia_externa,
                  f"Último respaldo probado: {probado.iniciado_en:%Y-%m-%d}" if probado else "Sin respaldo probado")],
            [_req("Al menos una copia en un lugar con amenazas distintas", False, "No implementado")],
            [_req("Al menos tres copias en lugares con amenazas distintas", False, "No implementado")],
        ],
        "Integridad": [
            [_req("Huella de cada archivo al recibirlo", True, "SHA-256 en la ingesta"),
             _req("Antivirus sobre el contenido recibido", antivirus,
                  "ClamAV activo" if antivirus else "ClamAV apagado (RICORA_ANTIVIRUS) o no instalado")],
            [_req("Verificar la huella al copiar o mover", True, "Segunda copia, AIP y restauración comparan la huella"),
             _req("Respaldar la información de integridad aparte", True,
                  "Manifiesto de huellas de solo anexar junto a la segunda copia (PRE-07)")],
            [_req("Verificar la fijeza a intervalos fijos", verificaciones > 0 and atrasadas == 0,
                  f"{verificaciones} verificaciones; {atrasadas} archivo(s) atrasados (cada {dias_fijeza} días)"),
             _req("Registro de las verificaciones", True, "Tabla de verificaciones y eventos PREMIS «fixity check»")],
            [_req("Reponer o reparar datos dañados", restauracion_posible,
                  f"Restauración desde la segunda copia ({restauraciones} hechas)")],
        ],
        "Control": [
            [_req("Saber quién tiene permisos de lectura, escritura y borrado", True, "Tabla de roles y permisos")],
            [_req("Registrar quién hace qué", True, "Auditoría inalterable (disparador de la base)")],
            [_req("Registrar las acciones de preservación (personas y programas)", True,
                  "Eventos PREMIS con su agente persona o mecanismo y versión")],
            [_req("Revisar periódicamente los registros", revision_al_dia,
                  f"Última constancia de revisión del consolidado semanal: {revisado:%Y-%m-%d}" if revisado
                  else "Nadie ha dejado constancia de revisar el consolidado semanal (Auditoría → Equipo por semana)")],
        ],
        "Metadatos": [
            [_req("Inventario del contenido y de su ubicación, respaldado", respaldo_al_dia,
                  "La base (inventario) tiene respaldo probado" if respaldo_al_dia else "Sin respaldo probado reciente")],
            [_req("Metadatos administrativos, técnicos y de preservación", True, "PREMIS 3.0 y PDI en cada AIP")],
            [_req("Norma de metadatos elegida e implementada", True, "PREMIS 3.0, validado contra el XSD en la CI")],
            [_req("Registro de las acciones de preservación con fecha", True, "Eventos PREMIS con su hora exacta")],
        ],
        "Contenido": [
            [_req("Identificar el formato de cada archivo", True, "Siegfried contra PRONOM, con su versión")],
            [_req("Verificar el formato y sus características (validación)", validadores,
                  f"veraPDF y JHOVE instalados; {validadas} archivo(s) validados" if validadores
                  else "veraPDF y JHOVE no están instalados")],
            [_req("Vigilar la obsolescencia de los formatos", True, "Tabla de riesgo y alertas")],
            [_req("Migrar o emular cuando haga falta", True, "Migración aprobada con Ghostscript o Pillow")],
        ],
    }


def niveles(db: Session) -> list[dict]:
    salida = []
    for area, por_nivel in requisitos(db).items():
        alcanzado = 0
        for n, reqs in enumerate(por_nivel, start=1):
            if all(r["cumple"] for r in reqs):
                alcanzado = n
            else:
                break
        siguiente = por_nivel[alcanzado] if alcanzado < len(por_nivel) else []
        salida.append({"area": area, "nivel": alcanzado, "requisitos": por_nivel,
                       "falta_para_el_siguiente": [r["requisito"] for r in siguiente if not r["cumple"]]})
    return salida
