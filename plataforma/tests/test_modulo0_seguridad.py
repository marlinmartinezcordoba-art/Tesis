"""Módulo transversal de autenticación, autorización y auditoría (sección 7
del prompt de desarrollo): contraseñas con bcrypt, sesión con expiración y
revocación, bloqueo por intentos, control por rol en todas las pantallas,
RegistroAuditoria con valores antes y después, y borrado lógico universal."""

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ric import auditoria_acciones, fusion
from ric.models import CorporateBody, FormaDocumental, ProveedorIAConfig, RegistroAuditoria, RelacionRiC

from ._ayudas import CasoModulos


class AutenticacionTest(CasoModulos):
    def test_contrasenas_con_bcrypt_y_login_valido_e_invalido(self):
        self.assertTrue(self.archivista.password.startswith("bcrypt_sha256$"))
        resp = self.client.post(reverse("ric_login"), {"username": "archivista", "password": "mala"})
        self.assertContains(resp, "Usuario o contraseña incorrectos")
        self.assertTrue(RegistroAuditoria.objects.filter(accion="login_fallido", detalle__usuario="archivista", exitoso=False).exists())
        resp = self.client.post(reverse("ric_login"), {"username": "archivista", "password": "x"})
        self.assertRedirects(resp, reverse("inicio"))
        registro = RegistroAuditoria.objects.get(accion="iniciar_sesion")
        self.assertEqual(registro.usuario, self.archivista)
        self.assertEqual(registro.object_id, self.archivista.pk)
        self.client.post(reverse("ric_logout"))
        self.assertTrue(RegistroAuditoria.objects.filter(accion="cerrar_sesion", usuario=self.archivista).exists())

    def test_bloqueo_tras_cinco_intentos_fallidos(self):
        for _ in range(auditoria_acciones.INTENTOS_MAXIMOS):
            self.client.post(reverse("ric_login"), {"username": "archivista", "password": "mala"})
        # el sexto intento, aun con la contraseña correcta, se rechaza sin comprobarla
        resp = self.client.post(reverse("ric_login"), {"username": "archivista", "password": "x"})
        self.assertContains(resp, "Demasiados intentos fallidos")
        self.assertTrue(RegistroAuditoria.objects.filter(accion="bloqueo_login", detalle__usuario="archivista").exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion="iniciar_sesion").exists())
        # otro usuario no queda bloqueado por los intentos de aquel
        resp = self.client.post(reverse("ric_login"), {"username": "revisor", "password": "x"})
        self.assertRedirects(resp, reverse("inicio"))

    def test_sesion_expira_por_inactividad_y_se_renueva_con_uso(self):
        from django.conf import settings

        self.assertEqual(settings.SESSION_COOKIE_AGE, 60 * 60)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.client.post(reverse("ric_login"), {"username": "archivista", "password": "x"})
        sesion = Session.objects.get(session_key=self.client.session.session_key)
        self.assertLessEqual(sesion.expire_date, timezone.now() + timezone.timedelta(hours=1, minutes=1))
        # sesión ya vencida: la siguiente petición exige entrar de nuevo
        sesion.expire_date = timezone.now() - timezone.timedelta(minutes=1)
        sesion.save()
        resp = self.client.get(reverse("ingesta"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("ric_login"), resp.url)

    def test_desactivar_o_restablecer_revoca_las_sesiones_abiertas(self):
        self.client.post(reverse("ric_login"), {"username": "revisor", "password": "x"})
        self.assertEqual(self.client.get(reverse("revision_lista")).status_code, 200)
        admin = self.client_class()
        admin.force_login(self.superusuario)
        admin.post(reverse("admin_usuario_editar", args=[self.revisor.pk]), {"accion": "desactivar"})
        self.assertEqual(self.client.get(reverse("revision_lista")).status_code, 302)  # sesión revocada
        registro = RegistroAuditoria.objects.get(accion="sesiones_cerradas", object_id=self.revisor.pk)
        self.assertEqual(registro.detalle["sesiones"], 1)
        self.assertEqual(registro.usuario, self.superusuario)
        admin.post(reverse("admin_usuario_editar", args=[self.revisor.pk]), {"accion": "reactivar"})
        self.client.post(reverse("ric_login"), {"username": "revisor", "password": "x"})
        admin.post(reverse("admin_usuario_editar", args=[self.revisor.pk]), {"accion": "restablecer"})
        self.assertEqual(self.client.get(reverse("revision_lista")).status_code, 302)
        # la contraseña (ni su hash) nunca queda en claro en la auditoría
        self.revisor.refresh_from_db()
        for r in RegistroAuditoria.objects.filter(object_id=self.revisor.pk):
            self.assertNotIn(self.revisor.password, str(r.antes) + str(r.despues) + str(r.detalle))


class AutorizacionTest(CasoModulos):
    def test_acceso_sin_permiso_se_niega_y_queda_en_auditoria(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("ingesta"), follow=True)
        self.assertContains(resp, "requiere el rol archivista")
        registro = RegistroAuditoria.objects.get(accion="acceso_denegado", usuario=self.consulta)
        self.assertEqual(registro.detalle["ruta"], reverse("ingesta"))
        self.assertFalse(registro.exitoso)
        resp = self.client.get(reverse("admin_usuarios"), follow=True)
        self.assertContains(resp, "Esta acción requiere")

    def test_acceso_con_permiso_por_cada_rol(self):
        self.client.force_login(self.revisor)
        for nombre in ("revision_lista", "valoracion", "catalogo"):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)
        self.client.force_login(self.archivista)
        self.assertEqual(self.client.get(reverse("ingesta")).status_code, 200)
        self.client.force_login(self.superusuario)
        self.assertEqual(self.client.get(reverse("admin_usuarios"), {"pestana": "auditoria"}).status_code, 200)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="acceso_denegado").exists())

    def test_sin_sesion_toda_pantalla_redirige_a_entrar(self):
        for nombre in ("panel", "ingesta", "analisis_lista", "vocabularios", "valoracion", "catalogo", "exportar", "admin_usuarios"):
            resp = self.client.get(reverse(nombre))
            self.assertEqual(resp.status_code, 302, nombre)
            self.assertIn(reverse("ric_login"), resp.url)


class AuditoriaTest(CasoModulos):
    def test_crear_y_modificar_guardan_antes_y_despues_con_el_usuario(self):
        self.client.force_login(self.archivista)
        self.client.post(reverse("vocabularios"), {"nombre": "Oficio", "definicion": "Comunicación oficial"})
        forma = FormaDocumental.objects.get(nombre="Oficio")
        creado = RegistroAuditoria.objects.get(accion="crear", object_id=forma.pk, content_type__model="formadocumental")
        self.assertEqual(creado.usuario, self.archivista)
        self.assertEqual(creado.despues["nombre"], "Oficio")
        self.client.post(reverse("vocabulario_ficha", args=["formadocumental", forma.pk]), {"nombre": "Oficio", "definicion": "Comunicación oficial externa", "serie_trd": ""})
        cambio = RegistroAuditoria.objects.get(accion="modificar", object_id=forma.pk, content_type__model="formadocumental")
        self.assertEqual(cambio.antes, {"definicion": "Comunicación oficial", "modificado_por": None})
        self.assertEqual(cambio.despues["definicion"], "Comunicación oficial externa")

    def test_pantalla_de_auditoria_filtra_y_exporta_csv(self):
        self.client.force_login(self.superusuario)
        self.client.post(reverse("admin_usuario_editar", args=[self.consulta.pk]), {"accion": "editar", "nombre_completo": "Consulta", "email": "consulta@entidad.gov.co", "rol": "revisor"})
        resp = self.client.get(reverse("admin_usuarios"), {"pestana": "auditoria", "accion": "modificar", "usuario": "marlin"})
        self.assertContains(resp, "<b>rol</b>: consulta → revisor")
        resp = self.client.get(reverse("admin_usuarios"), {"pestana": "auditoria", "accion": "modificar", "usuario": "nadie"})
        self.assertContains(resp, "Sin registros con ese filtro")
        resp = self.client.get(reverse("admin_auditoria_csv"), {"accion": "modificar"})
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")
        cuerpo = resp.content.decode("utf-8-sig")
        self.assertIn("'rol': 'revisor'", cuerpo)
        self.assertIn("marlin", cuerpo)
        self.client.force_login(self.archivista)
        self.assertContains(self.client.get(reverse("admin_auditoria_csv"), follow=True), "Esta acción requiere")


class BorradoLogicoTest(CasoModulos):
    def test_la_fusion_no_borra_fisicamente_y_se_puede_restaurar(self):
        a = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        b = CorporateBody.objects.create(nombre="Cabildo de Santa Fe")
        fusion.fusionar_entidades(b, a, usuario=self.archivista)
        self.assertFalse(CorporateBody.objects.filter(pk=b.pk).exists())  # invisible para el sistema
        borrada = CorporateBody.todos.get(pk=b.pk)  # pero sigue existiendo
        self.assertTrue(borrada.eliminado)
        self.assertEqual(borrada.eliminado_por, self.archivista)
        self.assertIn("Fusionada en", borrada.motivo_eliminacion)
        registro = RegistroAuditoria.objects.get(accion="eliminar", object_id=b.pk)
        self.assertEqual(registro.usuario, self.archivista)
        self.client.force_login(self.superusuario)
        resp = self.client.get(reverse("admin_usuarios"), {"pestana": "eliminados"})
        self.assertContains(resp, "Cabildo de Santa Fe")
        self.client.post(reverse("admin_restaurar"), {"modelo": "corporatebody", "pk": b.pk})
        self.assertTrue(CorporateBody.objects.filter(pk=b.pk).exists())
        self.assertTrue(RegistroAuditoria.objects.filter(accion="restaurar", object_id=b.pk, usuario=self.superusuario).exists())

    def test_eliminar_una_entidad_arrastra_sus_relaciones_y_el_grafo_las_oculta(self):
        record, _ = self.documento()
        [p] = self.proponer(record, __import__("tests._ayudas", fromlist=["candidato"]).candidato())
        p.validar(self.archivista, aceptar=True)
        cabildo = CorporateBody.objects.get(nombre="Cabildo de Santafé")
        self.assertEqual(RelacionRiC.objects.filter(destino_object_id=cabildo.pk).count(), 1)
        cabildo.eliminar(self.archivista, motivo="Entidad errónea")
        self.assertEqual(RelacionRiC.objects.filter(destino_object_id=cabildo.pk).count(), 0)
        self.assertEqual(RelacionRiC.todos.filter(destino_object_id=cabildo.pk, eliminado=True).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.get(accion="eliminar", object_id=cabildo.pk).detalle["relaciones"], 1)

    def test_forma_documental_eliminada_no_bloquea_el_nombre_ni_se_borra(self):
        oficio = FormaDocumental.objects.create(nombre="Oficio")
        oficios = FormaDocumental.objects.create(nombre="Oficios")
        fusion.fusionar_formas(oficios, oficio, usuario=self.archivista)
        self.assertTrue(FormaDocumental.todos.get(pk=oficios.pk).eliminado)
        FormaDocumental.objects.create(nombre="Oficios")  # el nombre vuelve a estar libre entre las activas
        self.assertEqual(FormaDocumental.objects.filter(nombre="Oficios").count(), 1)

    def test_proveedor_de_ia_se_retira_con_borrado_logico(self):
        config = ProveedorIAConfig.objects.create(proveedor="local-spacy", activo=True)
        self.client.force_login(self.superusuario)
        self.client.post(reverse("admin_proveedor_eliminar", args=[config.pk]))
        self.assertFalse(ProveedorIAConfig.objects.filter(pk=config.pk).exists())
        retirado = ProveedorIAConfig.todos.get(pk=config.pk)
        self.assertTrue(retirado.eliminado)
        self.assertFalse(retirado.activo)
