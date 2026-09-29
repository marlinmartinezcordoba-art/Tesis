"""IA local con Ollama: el proveedor (salida estructurada, errores en
lenguaje claro), la prueba de conexión, el respaldo automático cuando el
proveedor principal falla y el análisis en la cola. Ollama se simula con
httpx.MockTransport: las pruebas no necesitan red ni el modelo."""

import json
from unittest.mock import patch

import httpx
from django.test import override_settings
from django.urls import reverse

from ric import motor, proveedores
from ric.models import Instantiation, PropuestaRiC, ProveedorIAConfig
from ric.proveedor_ollama import ProveedorOllama
from ric.proveedores import ErrorProveedorIA

from ._ayudas import CasoModulos, ProveedorFalso, candidato

RESPUESTA_VALIDA = {
    "relaciones": [{
        "relacion_id": "R027", "entidad_tipo": "E11", "entidad_nombre": "Cabildo de Santafé",
        "evidencia": "Cabildo de Santafé", "confianza": "alta", "justificacion": "Produce el acta.",
        "rol_en_el_documento": "productor",
    }],
    "forma_documental": {"nombre_tipo": "acta", "confianza": "alta", "fragmento_fuente": "Acta de la sesión"},
    "advertencias": [],
}


def ollama_falso(chat=None, estado=200, tags=("qwen2.5:1.5b",), caido=False):
    pedidos = []

    def responder(request):
        if caido:
            raise httpx.ConnectError("sin conexión", request=request)
        pedidos.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": t} for t in tags]})
        if estado != 200:
            return httpx.Response(estado, json={"error": "model not found"})
        contenido = chat if isinstance(chat, str) else json.dumps(chat or RESPUESTA_VALIDA)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": contenido}, "done": True, "done_reason": "stop"})

    return httpx.Client(transport=httpx.MockTransport(responder)), pedidos


@override_settings(OLLAMA_URL="http://ollama:11434", RICORA_MODELO_OLLAMA="qwen2.5:1.5b")
class ProveedorOllamaTest(CasoModulos):
    def test_propone_con_salida_estructurada_y_pasa_por_las_reglas(self):
        record, _inst = self.documento()
        cliente, pedidos = ollama_falso()
        creadas = proveedores.generar_propuestas(record, ProveedorOllama(cliente=cliente))
        self.assertEqual(len(creadas), 1)
        self.assertEqual(creadas[0].entidad_nombre, "Cabildo de Santafé")
        self.assertEqual(creadas[0].proveedor, "ollama")
        cuerpo = json.loads(pedidos[0].content)
        self.assertEqual(cuerpo["model"], "qwen2.5:1.5b")
        self.assertFalse(cuerpo["stream"])
        self.assertIn("relaciones", cuerpo["format"]["properties"])  # JSON restringido al esquema RiC
        self.assertEqual(cuerpo["options"]["temperature"], 0)

    def test_evidencia_inventada_se_descarta_igual_que_con_la_nube(self):
        record, _inst = self.documento()
        falsa = json.loads(json.dumps(RESPUESTA_VALIDA))
        falsa["relaciones"][0]["evidencia"] = "texto que no está en el documento"
        cliente, _ = ollama_falso(chat=falsa)
        creadas = proveedores.generar_propuestas(record, ProveedorOllama(cliente=cliente))
        self.assertEqual(creadas[0].estado, PropuestaRiC.Estado.RECHAZADA)  # CC-01

    def test_errores_en_lenguaje_claro(self):
        record, _inst = self.documento()
        casos = [
            (ollama_falso(caido=True)[0], "no está disponible"),
            (ollama_falso(estado=404)[0], "todavía no está descargado"),
            (ollama_falso(chat="esto no es json")[0], "no cumple el formato"),
        ]
        for cliente, texto in casos:
            with self.assertRaisesMessage(ErrorProveedorIA, texto):
                ProveedorOllama(cliente=cliente).proponer(record, "Cabildo de Santafé")

    @override_settings(OLLAMA_URL="")
    def test_sin_ollama_configurado(self):
        record, _inst = self.documento()
        with self.assertRaisesMessage(ErrorProveedorIA, "falta OLLAMA_URL"):
            ProveedorOllama().proponer(record, "Cabildo de Santafé")

    def test_prueba_de_conexion(self):
        config = ProveedorIAConfig.objects.create(proveedor=ProveedorIAConfig.Proveedor.OLLAMA)
        for tags, esperado, texto in [(("qwen2.5:1.5b",), True, "Conexión correcta"), ((), False, "todavía no está descargado")]:
            cliente, _ = ollama_falso(tags=tags)
            with patch("ric.proveedor_ollama.ProveedorOllama.cliente", new=cliente):
                exitosa, mensaje = proveedores.probar_conexion(config)
            self.assertEqual(exitosa, esperado)
            self.assertIn(texto, mensaje)


class RespaldoTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()

    def _principal_saturado(self):
        class Saturado(ProveedorFalso):
            nombre, version = "gemini", "gemini-3.5-flash"

            def proponer(self, record, texto, instanciacion=None):
                raise ErrorProveedorIA("El servicio de IA está saturado en este momento (alta demanda).")
        return Saturado()

    def test_si_el_principal_falla_se_usa_el_respaldo_y_se_dice(self):
        respaldo = ProveedorFalso([candidato()])
        respaldo.nombre, respaldo.version = "ollama", "qwen2.5:1.5b"
        with patch("ric.proveedores.proveedor_activo", return_value=self._principal_saturado()), \
                patch("ric.proveedores.proveedor_respaldo", return_value=respaldo):
            resultado = motor.enviar_al_motor(self.record, self.archivista)
        self.assertEqual(resultado["propuestas"], 1)
        self.assertEqual(resultado["proveedor"], "ollama")
        self.assertIn("saturado", resultado["aviso_respaldo"])
        self.assertIn("respaldo ollama", resultado["aviso_respaldo"])

    def test_sin_respaldo_el_error_se_muestra_como_antes(self):
        with patch("ric.proveedores.proveedor_activo", return_value=self._principal_saturado()), \
                patch("ric.proveedores.proveedor_respaldo", return_value=None):
            resultado = motor.enviar_al_motor(self.record, self.archivista)
        self.assertIn("saturado", resultado["error"])

    def test_si_tambien_falla_el_respaldo_se_explican_los_dos(self):
        with patch("ric.proveedores.proveedor_activo", return_value=self._principal_saturado()), \
                patch("ric.proveedores.proveedor_respaldo", return_value=self._principal_saturado()):
            resultado = motor.enviar_al_motor(self.record, self.archivista)
        self.assertIn("el respaldo tampoco", resultado["error"])

    def test_respaldo_configurado_en_administracion(self):
        principal = ProveedorIAConfig.objects.create(proveedor=ProveedorIAConfig.Proveedor.GEMINI, activo=True)
        local = ProveedorIAConfig.objects.create(proveedor=ProveedorIAConfig.Proveedor.OLLAMA, prueba_exitosa=True)
        self.client.force_login(self.superusuario)
        self.client.post(reverse("admin_proveedor_activar", args=[local.pk]), {"accion": "respaldo"})
        local.refresh_from_db()
        self.assertTrue(local.es_respaldo)
        self.assertIsInstance(proveedores.proveedor_respaldo(), ProveedorOllama)
        self.assertFalse(ProveedorIAConfig.objects.get(pk=principal.pk).es_respaldo)
        resp = self.client.get("/admin/usuarios/?pestana=proveedores")
        self.assertContains(resp, "respaldo automático")
        self.assertContains(resp, "IA local con Ollama")

    def test_respaldo_exige_prueba_de_conexion(self):
        local = ProveedorIAConfig.objects.create(proveedor=ProveedorIAConfig.Proveedor.OLLAMA)
        self.client.force_login(self.superusuario)
        self.client.post(reverse("admin_proveedor_activar", args=[local.pk]), {"accion": "respaldo"})
        local.refresh_from_db()
        self.assertFalse(local.es_respaldo)

    def test_generar_propuesta_va_por_la_cola(self):
        self.client.force_login(self.archivista)
        with patch("ric.proveedores.proveedor_activo", return_value=ProveedorFalso([candidato()])):
            resp = self.client.post(reverse("analisis_generar", args=[self.record.pk]), follow=True)
        self.inst.refresh_from_db()
        self.assertEqual(self.inst.estado_proceso, Instantiation.EstadoProceso.LISTO)
        self.assertEqual(self.inst.resultado_proceso["analisis"]["propuestas"], 1)
        self.assertContains(resp, "1 propuesta(s) nueva(s)")

    def test_mientras_analiza_la_pagina_lo_dice_y_bloquea_el_boton(self):
        Instantiation.objects.filter(pk=self.inst.pk).update(estado_proceso=Instantiation.EstadoProceso.PROCESANDO, etapa="Enviando al motor de análisis")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("analisis", args=[self.record.pk]))
        self.assertContains(resp, "El motor de análisis está trabajando en este documento")
        self.assertContains(resp, "location.reload()")
