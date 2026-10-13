"""Pruebas sin conexión a Clever Cloud ni MongoDB Atlas.

Ejecutar: python -m unittest discover -s tests -v
"""

import os
import unittest
from unittest.mock import patch

# Configuración de prueba sin credenciales de producción.
os.environ["SECRET_KEY"] = "clave-secreta-solo-para-pruebas-locales-123456789"
os.environ["MONGO_URI"] = "mongodb://127.0.0.1:27017/"
os.environ["MONGO_DB"] = "sistema_auth_test"

import app as modulo  # noqa: E402


class PruebasAutenticacion(unittest.TestCase):
    def setUp(self):
        modulo.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SESSION_COOKIE_SECURE=False)
        self.cliente = modulo.app.test_client()

    def test_validacion(self):
        self.assertTrue(modulo.correo_valido("alguien@ejemplo.com"))
        self.assertFalse(modulo.correo_valido("correo_invalido"))
        self.assertFalse(modulo.clave_valida("corta"))
        self.assertTrue(modulo.clave_valida("esta-es-segura"))

    def test_registro_no_permite_contrasenas_diferentes(self):
        with patch.object(modulo, "crear_usuario") as crear:
            resultado = self.cliente.post(
                "/registro",
                data={
                    "nombre": "Usuario",
                    "correo": "usuario@ejemplo.com",
                    "clave": "esta-es-mi-clave",
                    "confirmar": "otra-clave-distinta",
                },
            )
        self.assertEqual(resultado.status_code, 200)
        self.assertIn(b"Las contrase", resultado.data)
        crear.assert_not_called()

    def test_registro_valido(self):
        with patch.object(modulo, "crear_usuario", return_value=42) as crear:
            with patch.object(modulo, "registrar_log") as registro:
                resultado = self.cliente.post(
                    "/registro",
                    data={
                        "nombre": "Usuario",
                        "correo": "usuario@ejemplo.com",
                        "clave": "esta-es-mi-clave",
                        "confirmar": "esta-es-mi-clave",
                    },
                )
        self.assertEqual(resultado.status_code, 302)
        self.assertTrue(resultado.location.endswith("/login"))
        crear.assert_called_once_with(
            "Usuario", "usuario@ejemplo.com", "esta-es-mi-clave", rol="usuario"
        )
        registro.assert_called_once_with("registro_usuario", 42)

    def test_login_incorrecto(self):
        with patch.object(modulo, "buscar_correo", return_value=None):
            with patch.object(modulo, "registrar_log") as registro:
                resultado = self.cliente.post(
                    "/login", data={"correo": "nadie@ejemplo.com", "clave": "incorrecta"}
                )
        self.assertEqual(resultado.status_code, 200)
        self.assertIn(b"Correo o contrase", resultado.data)
        registro.assert_called_once_with("login_fallido", None)

    def test_login_panel_logout(self):
        clave = "clave-larga-valida"
        usuario = {
            "id": 3,
            "correo": "usuario@ejemplo.com",
            "rol": "usuario",
            "clave_hash": modulo.bcrypt.hashpw(
                clave.encode(), modulo.bcrypt.gensalt(rounds=4)
            ).decode(),
        }
        with patch.object(modulo, "buscar_correo", return_value=usuario):
            with patch.object(modulo, "registrar_log"):
                ingreso = self.cliente.post(
                    "/login", data={"correo": usuario["correo"], "clave": clave}
                )
        self.assertEqual(ingreso.status_code, 302)
        self.assertTrue(ingreso.location.endswith("/panel"))

        with patch.object(modulo, "consultar_uno", return_value=usuario):
            with patch.object(
                modulo.perfiles, "find_one", return_value={"nombre": "Usuario"}
            ):
                panel = self.cliente.get("/panel")
                self.assertEqual(panel.status_code, 200)
                self.assertIn(b"Usuario", panel.data)

                with patch.object(modulo, "registrar_log") as registro:
                    salida = self.cliente.post("/logout")
                self.assertEqual(salida.status_code, 302)
                registro.assert_called_once_with("logout", 3)

        protegido = self.cliente.get("/panel")
        self.assertEqual(protegido.status_code, 302)
        self.assertIn("/login", protegido.location)

    def test_usuario_no_puede_entrar_a_admin(self):
        clave = "clave-larga-valida"
        usuario = {
            "id": 5,
            "correo": "u@ejemplo.com",
            "rol": "usuario",
            "clave_hash": modulo.bcrypt.hashpw(
                clave.encode(), modulo.bcrypt.gensalt(rounds=4)
            ).decode(),
        }
        with patch.object(modulo, "buscar_correo", return_value=usuario):
            with patch.object(modulo, "registrar_log"):
                ingreso = self.cliente.post(
                    "/login", data={"correo": usuario["correo"], "clave": clave}
                )
        self.assertEqual(ingreso.status_code, 302)
        with patch.object(modulo, "consultar_uno", return_value=usuario):
            respuesta = self.cliente.get("/admin")
        self.assertEqual(respuesta.status_code, 403)


if __name__ == "__main__":
    unittest.main()
