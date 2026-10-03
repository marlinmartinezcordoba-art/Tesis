"""
Configuración centralizada, leída de variables de entorno. Una instancia
por entidad, variables en un archivo .env propio de cada despliegue (ver
.env.example), nunca credenciales reales dentro del código.
"""

import os
from pathlib import Path


def _entero(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


def _booleano(nombre: str, defecto: bool = False) -> bool:
    valor = os.getenv(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes")


class Settings:
    nombre_sistema: str = "RICORA"

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://ricora:ricora@localhost:5432/ricora",
    )

    # Carpeta donde se guardan los archivos ingestados. En producción es un
    # volumen de Docker.
    directorio_almacenamiento: Path = Path(os.getenv("DIRECTORIO_ALMACENAMIENTO", "/data/almacen"))

    # Segunda copia (preservación, OAIS Almacenamiento de Archivo): lugares
    # donde el administrador puede elegir guardarla, separados por «:». Los
    # declara quien opera el servidor (no se escriben rutas desde la web);
    # cada uno debe estar fuera de DIRECTORIO_ALMACENAMIENTO. En producción
    # real conviene un disco o servidor distinto montado en una de ellas.
    ubicaciones_segunda_copia: list[Path] = [Path(p) for p in os.getenv(
        "RICORA_SEGUNDA_COPIA", "/data/segunda_copia").split(os.pathsep) if p.strip()]

    # La web monta la segunda copia en solo lectura: nunca escribe en ella
    # (la crea el trabajador). Así un error de la aplicación web no puede
    # dañar a la vez las dos copias.
    segunda_copia_solo_lectura: bool = os.getenv("RICORA_SEGUNDA_COPIA_SOLO_LECTURA", "0") == "1"

    # Respaldo de la base de datos (pg_dump) y su simulacro de restauración.
    # En producción real, un disco o almacenamiento de otro equipo montado
    # aquí; además, el administrador descarga cada cierto tiempo el último
    # respaldo a su propio equipo (copia fuera del servidor, sin costo).
    directorio_respaldo: Path = Path(os.getenv("RICORA_RESPALDO", "/data/respaldo"))
    pg_dump: str = os.getenv("RICORA_PG_DUMP", "pg_dump")
    pg_restore: str = os.getenv("RICORA_PG_RESTORE", "pg_restore")

    # --- Ingesta ---
    # Identificador de formato contra PRONOM (Siegfried): binario y carpeta
    # con el archivo de firmas (default.sig).
    siegfried_binario: str = os.getenv("RICORA_SIEGFRIED", "sf")
    siegfried_home: str = os.getenv("RICORA_SIEGFRIED_HOME", "/opt/siegfried")
    # Preservación: conversión a PDF/A.
    ghostscript_binario: str = os.getenv("RICORA_GHOSTSCRIPT", "gs")
    # Idioma del reconocimiento óptico de caracteres (Tesseract).
    idioma_ocr: str = os.getenv("RICORA_IDIOMA_OCR", "spa")
    # Resolución a la que se pasa a imagen cada página de un PDF escaneado.
    dpi_ocr: int = _entero("RICORA_DPI_OCR", 300)
    # Tiempo máximo por página de OCR o por identificación de formato.
    segundos_por_paso: int = _entero("RICORA_SEGUNDOS_POR_PASO", 300)

    # --- Descripción ---
    # Motor de análisis: Gemini (clave de Google AI Studio). Sin clave, la
    # descripción funciona igual pero sin propuestas automáticas.
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    modelo_ia: str = os.getenv("RICORA_MODELO_IA", "gemini-3.5-flash")
    segundos_motor: int = _entero("RICORA_SEGUNDOS_MOTOR", 90)
    # Por debajo de esta confianza, una propuesta se marca «confianza baja».
    umbral_confianza: float = float(os.getenv("UMBRAL_CONFIANZA_REVISION", "0.70"))
    # Similitud por trigramas desde la cual el vocabulario sugiere «¿es la misma?».
    umbral_similitud: float = float(os.getenv("UMBRAL_SIMILITUD_VOCABULARIO", "0.45"))
    # Tiempo sin actividad tras el cual se libera la marca «en edición».
    minutos_bloqueo_descripcion: int = _entero("MINUTOS_BLOQUEO_DESCRIPCION", 30)

    # Clave con la que se firman los tokens de sesión. Sin ella el sistema
    # no arranca en producción (ver app/main.py).
    secret_key: str = os.getenv("RICORA_SECRET_KEY", "")

    # Dirección pública con la que se arman los enlaces que se envían por
    # correo (invitación y recuperación). Se fija por configuración y no se
    # toma del encabezado Host de la petición, para que nadie pueda hacer
    # que el sistema envíe un enlace hacia otro servidor.
    url_publica: str = os.getenv("RICORA_URL_PUBLICA", "http://localhost:8000").rstrip("/")

    # --- Vigencias (ver documentacion/modulo-autenticacion.md, decisiones) ---
    # Token de acceso: corto, se renueva solo mientras la persona trabaja.
    minutos_token_acceso: int = _entero("MINUTOS_TOKEN_ACCESO", 15)
    # Sesión: se cierra tras este tiempo sin ninguna actividad...
    minutos_inactividad_sesion: int = _entero("MINUTOS_INACTIVIDAD_SESION", 60)
    # ...y en todo caso tras este máximo desde que se abrió.
    horas_maximas_sesion: int = _entero("HORAS_MAXIMAS_SESION", 10)
    # Zona horaria del equipo: define los días y las semanas del panel de auditoría.
    zona_horaria: str = os.getenv("RICORA_ZONA_HORARIA", "America/Bogota")
    # Enlace de recuperación de contraseña.
    minutos_token_recuperacion: int = _entero("MINUTOS_TOKEN_RECUPERACION", 30)
    # Enlace de invitación a una cuenta nueva.
    horas_token_invitacion: int = _entero("HORAS_TOKEN_INVITACION", 72)

    # Bloqueo por intentos fallidos de inicio de sesión.
    intentos_fallidos_maximos: int = _entero("INTENTOS_FALLIDOS_MAXIMOS", 5)
    minutos_bloqueo: int = _entero("MINUTOS_BLOQUEO", 15)
    # Solicitudes de recuperación por dirección IP y por hora.
    recuperaciones_por_hora: int = _entero("RECUPERACIONES_POR_HORA", 5)

    # La galleta de renovación solo viaja por HTTPS cuando esto está activo.
    galleta_segura: bool = _booleano("RICORA_GALLETA_SEGURA", False)

    # --- Correo transaccional (SMTP) ---
    correo_servidor: str = os.getenv("EMAIL_HOST", "")
    correo_puerto: int = _entero("EMAIL_PORT", 587)
    correo_usuario: str = os.getenv("EMAIL_HOST_USER", "")
    correo_contrasena: str = os.getenv("EMAIL_HOST_PASSWORD", "")
    correo_remitente: str = os.getenv("EMAIL_REMITENTE", "")
    correo_tiempo_espera: int = _entero("EMAIL_TIMEOUT", 20)

    # Carpeta con la interfaz ya compilada (React). En desarrollo la sirve
    # Vite; en producción la sirve el mismo backend.
    directorio_interfaz: Path = Path(os.getenv("RICORA_DIRECTORIO_INTERFAZ", "/app/interfaz"))

    @property
    def correo_configurado(self) -> bool:
        return bool(self.correo_servidor and self.correo_usuario and self.correo_contrasena)

    @property
    def remitente(self) -> str:
        return self.correo_remitente or f"RICORA <{self.correo_usuario}>"


settings = Settings()
