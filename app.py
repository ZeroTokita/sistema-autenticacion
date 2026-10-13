"""Sistema académico de autenticación: MySQL (cuentas) + MongoDB (perfiles y logs)."""

import getpass
import os
import re
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import click
import mysql.connector
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf.csrf import CSRFProtect
from pymongo import MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

app = Flask(__name__)

secret = os.getenv("SECRET_KEY", "")
if len(secret) < 32:
    raise RuntimeError("Configura SECRET_KEY con al menos 32 caracteres en .env")

app.config.update(
    SECRET_KEY=secret,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    MAX_CONTENT_LENGTH=64 * 1024,
)

csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Debes iniciar sesión para continuar."
login_manager.login_message_category = "error"
login_manager.session_protection = "strong"

# Al desarrollar en una sola PC es suficiente. En producción usar almacenamiento
# compartido (por ejemplo Redis) para mantener los límites entre procesos.
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")

mongo_uri = os.getenv("MONGO_URI", "")
if not mongo_uri:
    raise RuntimeError("Configura MONGO_URI en el archivo .env")

mongo = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000, connect=False)
mongo_db = mongo[os.getenv("MONGO_DB", "sistema_auth")]
perfiles = mongo_db["perfiles"]
logs = mongo_db["logs"]

# Permite una verificación constante aunque el correo no exista.
HASH_FALSO = bcrypt.hashpw(b"clave-para-comparacion", bcrypt.gensalt(rounds=12))


def conexion_mysql():
    """Conecta a la base que ya existe en el add-on de Clever Cloud."""
    config = {
        "host": os.environ["MYSQL_HOST"],
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.environ["MYSQL_DATABASE"],
        "connection_timeout": 10,
    }
    # Un CA configurado permite verificar el certificado de MySQL.
    ca = os.getenv("MYSQL_SSL_CA", "").strip()
    if ca:
        config.update(
            ssl_ca=ca,
            ssl_verify_cert=True,
            ssl_verify_identity=True,
        )
    return mysql.connector.connect(**config)


def consultar_uno(sql, parametros=()):
    conexion = conexion_mysql()
    try:
        cursor = conexion.cursor(dictionary=True)
        try:
            cursor.execute(sql, parametros)
            return cursor.fetchone()
        finally:
            cursor.close()
    finally:
        conexion.close()


def consultar_todos(sql, parametros=()):
    conexion = conexion_mysql()
    try:
        cursor = conexion.cursor(dictionary=True)
        try:
            cursor.execute(sql, parametros)
            return cursor.fetchall()
        finally:
            cursor.close()
    finally:
        conexion.close()


def buscar_correo(correo):
    return consultar_uno(
        "SELECT id, correo, clave_hash, rol FROM usuarios WHERE correo = %s",
        (correo,),
    )


def correo_valido(correo):
    if not isinstance(correo, str) or len(correo) > 190:
        return False
    return re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", correo) is not None


def clave_valida(clave):
    return isinstance(clave, str) and len(clave) >= 10 and len(clave.encode("utf-8")) <= 72


def registrar_log(accion, usuario_id=None):
    """La falla del registro de actividad no bloquea la autenticación."""
    try:
        logs.insert_one(
            {"accion": accion, "usuario_id": usuario_id, "fecha": datetime.now(timezone.utc)}
        )
    except PyMongoError:
        app.logger.exception("No se pudo registrar el evento %s", accion)


def crear_usuario(nombre, correo, clave, rol="usuario"):
    """Registra credenciales en MySQL y perfil en MongoDB.

    No existe una transacción atómica entre MySQL y MongoDB: ante una falla se
    revierte MySQL y, si se insertó el perfil, se intenta eliminarlo.
    """
    if rol not in ("usuario", "admin"):
        raise ValueError("Rol no permitido")
    if not 1 <= len(nombre) <= 80 or not correo_valido(correo) or not clave_valida(clave):
        raise ValueError("Datos de registro inválidos")

    clave_hash = bcrypt.hashpw(
        clave.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")

    conexion = conexion_mysql()
    cursor = None
    usuario_id = None
    perfil_creado = False
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO usuarios (correo, clave_hash, rol) VALUES (%s, %s, %s)",
            (correo, clave_hash, rol),
        )
        usuario_id = cursor.lastrowid
        perfiles.insert_one(
            {
                "usuario_id": usuario_id,
                "nombre": nombre,
                "biografia": "",
                "creado_en": datetime.now(timezone.utc),
            }
        )
        perfil_creado = True
        conexion.commit()
        return usuario_id
    except Exception:
        try:
            conexion.rollback()
        except mysql.connector.Error:
            app.logger.exception("No se pudo revertir MySQL")
        if perfil_creado:
            try:
                perfiles.delete_one({"usuario_id": usuario_id})
            except PyMongoError:
                app.logger.exception("No se pudo compensar MongoDB")
        raise
    finally:
        if cursor is not None:
            cursor.close()
        conexion.close()


class Usuario(UserMixin):
    def __init__(self, datos):
        self.id = str(datos["id"])
        self.correo = datos["correo"]
        self.rol = datos["rol"]


@login_manager.user_loader
def cargar_usuario(usuario_id):
    if not usuario_id.isdecimal():
        return None
    datos = consultar_uno(
        "SELECT id, correo, rol FROM usuarios WHERE id = %s",
        (int(usuario_id),),
    )
    return Usuario(datos) if datos else None


def solo_admin(funcion):
    @wraps(funcion)
    @login_required
    def protegida(*args, **kwargs):
        if current_user.rol != "admin":
            abort(403)
        return funcion(*args, **kwargs)
    return protegida


@app.get("/")
def inicio():
    return redirect(url_for("panel" if current_user.is_authenticated else "login"))


@app.route("/registro", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("panel"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        clave = request.form.get("clave", "")
        confirmar = request.form.get("confirmar", "")

        if not 1 <= len(nombre) <= 80:
            flash("El nombre debe tener entre 1 y 80 caracteres.", "error")
        elif not correo_valido(correo):
            flash("Introduce un correo válido.", "error")
        elif not clave_valida(clave):
            flash("La contraseña debe tener 10 o más caracteres (máximo 72 bytes).", "error")
        elif clave != confirmar:
            flash("Las contraseñas no coinciden.", "error")
        else:
            try:
                usuario_id = crear_usuario(nombre, correo, clave, rol="usuario")
            except mysql.connector.IntegrityError:
                flash("Ese correo ya está registrado.", "error")
            except (mysql.connector.Error, PyMongoError):
                app.logger.exception("Error al registrar usuario")
                flash("No se pudo completar el registro. Intenta más tarde.", "error")
            else:
                registrar_log("registro_usuario", usuario_id)
                flash("Cuenta creada correctamente. Inicia sesión.", "exito")
                return redirect(url_for("login"))

    return render_template("registro.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("panel"))

    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        clave_bytes = request.form.get("clave", "").encode("utf-8")
        try:
            usuario = buscar_correo(correo)
        except mysql.connector.Error:
            app.logger.exception("MySQL no disponible durante login")
            flash("No fue posible verificar el inicio de sesión.", "error")
            return render_template("login.html"), 503

        hash_guardado = (
            usuario["clave_hash"].encode("utf-8") if usuario else HASH_FALSO
        )
        correcta = False
        if len(clave_bytes) <= 72:
            try:
                correcta = bcrypt.checkpw(clave_bytes, hash_guardado)
            except (ValueError, TypeError):
                app.logger.exception("El hash almacenado no tiene formato bcrypt válido")

        if usuario and correcta:
            session.clear()
            session.permanent = True
            login_user(Usuario(usuario), remember=False)
            registrar_log("login_exitoso", usuario["id"])
            flash("Sesión iniciada correctamente.", "exito")
            return redirect(url_for("panel"))

        registrar_log("login_fallido", usuario["id"] if usuario else None)
        flash("Correo o contraseña incorrectos.", "error")

    return render_template("login.html")


@app.get("/panel")
@login_required
def panel():
    try:
        perfil_usuario = perfiles.find_one({"usuario_id": int(current_user.id)}) or {}
    except PyMongoError:
        app.logger.exception("No se pudo cargar el perfil")
        flash("No se pudo obtener el perfil desde MongoDB.", "error")
        perfil_usuario = {}
    return render_template("panel.html", perfil=perfil_usuario)


@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    usuario_id = int(current_user.id)
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        biografia = request.form.get("biografia", "").strip()

        if not 1 <= len(nombre) <= 80:
            flash("El nombre debe tener entre 1 y 80 caracteres.", "error")
        elif len(biografia) > 500:
            flash("La biografía no puede superar 500 caracteres.", "error")
        else:
            try:
                perfiles.update_one(
                    {"usuario_id": usuario_id},
                    {"$set": {"nombre": nombre, "biografia": biografia}},
                    upsert=True,
                )
            except PyMongoError:
                app.logger.exception("No se pudo actualizar el perfil")
                flash("No se pudo guardar el perfil.", "error")
            else:
                registrar_log("perfil_editado", usuario_id)
                flash("Perfil actualizado correctamente.", "exito")
                return redirect(url_for("panel"))

    try:
        datos = perfiles.find_one({"usuario_id": usuario_id}) or {}
    except PyMongoError:
        app.logger.exception("No se pudo cargar la edición del perfil")
        flash("Error al consultar MongoDB.", "error")
        datos = {}
    return render_template("perfil.html", perfil=datos)


@app.post("/logout")
@login_required
def logout():
    registrar_log("logout", int(current_user.id))
    logout_user()
    session.clear()
    flash("Sesión cerrada correctamente.", "exito")
    return redirect(url_for("login"))


@app.get("/admin")
@solo_admin
def admin():
    try:
        usuarios = consultar_todos(
            "SELECT id, correo, rol, creado_en FROM usuarios ORDER BY id DESC"
        )
        actividades = list(
            logs.find({}, {"_id": 0}).sort("fecha", -1).limit(20)
        )
    except (mysql.connector.Error, PyMongoError):
        app.logger.exception("Error al mostrar administración")
        flash("No fue posible consultar la administración.", "error")
        return redirect(url_for("panel"))
    return render_template("admin.html", usuarios=usuarios, actividades=actividades)


@app.cli.command("crear-admin")
def crear_admin():
    """Crear un administrador de forma local, nunca desde el registro web."""
    nombre = click.prompt("Nombre completo").strip()
    correo = click.prompt("Correo electrónico").strip().lower()
    clave = getpass.getpass("Contraseña: ")

    if not 1 <= len(nombre) <= 80 or not correo_valido(correo) or not clave_valida(clave):
        raise click.ClickException("Nombre, correo o contraseña inválidos")
    try:
        usuario_id = crear_usuario(nombre, correo, clave, rol="admin")
    except mysql.connector.IntegrityError as exc:
        raise click.ClickException("El correo ya está registrado") from exc
    except (mysql.connector.Error, PyMongoError) as exc:
        raise click.ClickException("No se pudo crear el administrador") from exc

    registrar_log("admin_creado", usuario_id)
    click.echo("Administrador creado correctamente.")


@app.after_request
def cabeceras_seguridad(respuesta):
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


if __name__ == "__main__":
    app.run(debug=False)
