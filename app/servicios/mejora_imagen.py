"""
Mejora de la imagen de una página escaneada antes del OCR.

Los documentos antiguos llegan escaneados con sombras, fondo amarillento, manchas y letras
desvaídas. Antes de reconocer el texto, cada página se limpia:

1. Escala de grises.
2. Se quita el fondo: se estima cómo es el papel sin las letras (la página reducida, con un
   filtro de máximo que borra el trazo oscuro y un desenfoque) y se divide la página por ese
   fondo. Las sombras del borde, el amarillo y los pliegues quedan blancos y las letras
   conservan su contraste.
3. Se estira el contraste (lo más claro a blanco, lo más oscuro a negro).
4. Binarización con el umbral de Otsu, calculado sobre el histograma de la página: cada píxel
   queda blanco (papel) o negro (tinta).
5. Se quitan las motas sueltas con un filtro de mediana.

La página conserva su tamaño, así las posiciones de cada palabra del OCR siguen coincidiendo con
el original (la evidencia que se cita). Solo se usa Pillow: no hace falta OpenCV ni numpy.

El original nunca se modifica: la imagen mejorada se usa para leer el texto y para la copia de
consulta con OCR estampado, que es otra instanciación, derivada del original.
"""

from PIL import Image, ImageFilter, ImageMath, ImageOps

ESCALA_FONDO = 16  # el fondo se estima en una copia 16 veces más pequeña (rápido y suave)


def _umbral_otsu(imagen: Image.Image) -> int:
    """El umbral que mejor separa papel y tinta según el histograma (método de Otsu)."""
    histograma = imagen.histogram()[:256]
    total = sum(histograma)
    if not total:
        return 128
    suma_total = sum(i * n for i, n in enumerate(histograma))
    suma_fondo = peso_fondo = 0
    mejor, umbral = -1.0, 128
    for i, n in enumerate(histograma):
        peso_fondo += n
        if peso_fondo == 0:
            continue
        peso_frente = total - peso_fondo
        if peso_frente == 0:
            break
        suma_fondo += i * n
        media_fondo = suma_fondo / peso_fondo
        media_frente = (suma_total - suma_fondo) / peso_frente
        varianza = peso_fondo * peso_frente * (media_fondo - media_frente) ** 2
        if varianza > mejor:
            mejor, umbral = varianza, i
    return umbral


def sin_fondo(imagen: Image.Image) -> Image.Image:
    """La página en grises con el fondo (sombras, amarillo, manchas grandes) llevado a blanco."""
    gris = imagen.convert("L")
    ancho, alto = gris.size
    pequena = gris.resize((max(1, ancho // ESCALA_FONDO), max(1, alto // ESCALA_FONDO)), Image.Resampling.BOX)
    fondo = pequena.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(2))
    fondo = fondo.resize((ancho, alto), Image.Resampling.BILINEAR)
    normal = ImageMath.lambda_eval(lambda a: a["convert"](a["min"](a["g"] * 255 / (a["f"] + 1), 255), "L"),
                                   g=gris, f=fondo)
    return ImageOps.autocontrast(normal, cutoff=1)


def mejorar(imagen: Image.Image, binarizar: bool = True) -> Image.Image:
    """La página limpia para el OCR: sin fondo, con contraste y, si `binarizar`, en blanco y negro."""
    limpia = sin_fondo(imagen)
    if not binarizar:
        return limpia
    umbral = _umbral_otsu(limpia)
    blanco_negro = limpia.point(lambda v: 255 if v > umbral else 0)
    return blanco_negro.filter(ImageFilter.MedianFilter(3))


def mejorar_archivo(origen, destino) -> None:
    """Lee una imagen, la mejora y la guarda (PNG)."""
    with Image.open(origen) as img:
        mejorar(img).save(destino)
