# Sistema de Autenticación: Python + MySQL + MongoDB

Aplicación académica desarrollada en **Python / Flask**. Usa **MySQL de Clever Cloud** para credenciales y roles, y **MongoDB Atlas** para perfiles y registros de actividad. La interfaz incluye registro, login, panel protegido, edición del perfil, logout y vista administrativa.

## Requisitos

- Windows y Python **3.11** instalado.
- Una base MySQL existente en **Clever Cloud** con la tabla `usuarios`.
- Un clúster de MongoDB Atlas con la base **`sistema_auth`** y colecciones `perfiles` y `logs`.
- Tu IP autorizada en **Network Access** de Atlas; usuario de base de datos con permisos `readWrite` en `sistema_auth`.

## 1. Abrir proyecto e instalar dependencias

En VS Code, abre la carpeta que contiene `app.py`. En PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> No incluyas tu carpeta `.venv` en GitHub o en el ZIP de entrega. Se reconstruye con `requirements.txt`.

## 2. Configurar `.env`

Copia `.env.example` como `.env` y escribe tus credenciales **reales** (Clever Cloud y Atlas). En el ZIP corregido **no se incluyen credenciales**, aunque hubieras cambiado las del proyecto original. Conserve tu archivo `.env` local original si sigue funcionando.

Usa el **puerto real** de Clever Cloud (no asumas 3306). La `MONGO_URI` la obtienes de Atlas: `Clusters → Connect → Drivers → Python`.

Crea una clave secreta ejecutando:

```powershell
py -3.11 -c "import secrets; print(secrets.token_hex(32))"
```

Pega el valor en `SECRET_KEY` de `.env`. En desarrollo local usa `COOKIE_SECURE=0`. Para servir por HTTPS usa `COOKIE_SECURE=1`.

**Seguridad:** jamás envíes `.env` a GitHub ni publiques capturas con contraseñas, claves o URI de conexión. Si una clave se expuso, cámbiala en el proveedor.

## 3. Preparar las bases de datos (solo la primera vez)

**MySQL Clever Cloud:** la tabla `usuarios` ya debería existir. Si no existe, ejecuta:

```powershell
.\.venv\Scripts\python.exe crear_tabla.py
```

Este comando ejecuta `schema.sql` y verifica el esquema. `CREATE TABLE IF NOT EXISTS` no cambia una tabla existente distinta; comprueba que tenga las columnas `id`, `correo`, `clave_hash`, `rol`, `creado_en`.

**MongoDB Atlas:** si las colecciones `perfiles` y `logs` ya existen, no las recrees. Ejecuta una vez para crear los índices:

```powershell
.\.venv\Scripts\python.exe inicializar_mongo.py
```

Crea un índice único en `perfiles.usuario_id` y un índice en `logs.fecha`. Si tu colección ya tiene perfiles duplicados, será necesario resolverlos antes de crear el índice único.

Para volver a verificar las conexiones:

```powershell
.\.venv\Scripts\python.exe probar_mysql.py
.\.venv\Scripts\python.exe probar_mongo.py
```

## 4. Iniciar aplicación web

```powershell
.\.venv\Scripts\python.exe app.py
```

Abre: **http://127.0.0.1:5000/** (redirige a login) o **http://127.0.0.1:5000/registro**.

| Ruta | Funcionalidad | Acceso |
| --- | --- | --- |
| `/registro` | Crear cuenta en MySQL y perfil en MongoDB | Público |
| `/login` | Validar contraseña bcrypt y abrir sesión | Público |
| `/panel` | Mostrar datos de ambas bases | Requiere login |
| `/perfil` | Editar nombre/biografía en MongoDB | Requiere login |
| `/logout` | Cerrar sesión y registrar actividad | Requiere login, POST |
| `/admin` | Listado de usuarios y últimos 20 logs | Solo rol admin |

El registro público **solo** crea cuentas de rol `usuario`, nunca `admin`.

## 5. Crear cuenta de administrador

Con las bases configuradas, en PowerShell:

```powershell
.\.venv\Scripts\python.exe -m flask --app app crear-admin
```

Responde las preguntas de nombre, correo y contraseña. El comando no muestra la contraseña mientras escribes. Luego inicia sesión como administrador y entra a `/admin`.

## 6. Pruebas paso a paso y capturas

1. Abre `/registro` y registra un usuario con nombre, correo y contraseña de **10 caracteres o más**. Confirma exactamente la misma contraseña.
2. Consulta MySQL y verifica el registro:
   ```sql
   SELECT id, correo, clave_hash, rol, creado_en FROM usuarios;
   ```
   El hash debe comenzar normalmente con `$2b$` (bcrypt) y el rol debe ser `usuario`.
3. En MongoDB Atlas → Data Explorer → `sistema_auth.perfiles`, comprueba el documento vinculado por `usuario_id`.
4. En `/login`, prueba una contraseña incorrecta y luego una correcta. Verifica la redirección a `/panel`.
5. En `/perfil`, modifica nombre y biografía. Refresca `perfiles` en Atlas y verifica el cambio.
6. Presiona **Cerrar sesión**. Intenta entrar a `/panel` sin sesión y verifica que vuelva a login.
7. Usa `crear-admin`, inicia sesión como admin y abre `/admin`. Como usuario normal, acceder a `/admin` debe devolver HTTP 403.
8. En Atlas → `sistema_auth.logs`, captura `registro_usuario`, `login_exitoso`, `login_fallido`, `perfil_editado` y `logout` según tus pruebas.

Guarda las imágenes en `evidencias/` si deseas agregarlas al repositorio. Las capturas **deben ser reales** de tu ejecución; no vienen incluidas.

## 7. Estructura del proyecto

```text
sistema-autenticacion/
├── app.py                 # Flask, rutas, seguridad y acceso a las dos bases
├── templates/
│   ├── base.html
│   ├── registro.html
│   ├── login.html
│   ├── panel.html
│   ├── perfil.html
│   └── admin.html
├── static/estilos.css
├── schema.sql             # Tabla usuarios de MySQL
├── mongo_setup.js         # Alternativa para mongosh
├── inicializar_mongo.py   # Creación de índices desde Python
├── crear_tabla.py         # Script inicial MySQL
├── probar_mysql.py        # Prueba de conexión MySQL
├── probar_mongo.py        # Prueba de conexión MongoDB
├── requirements.txt
├── .env.example           # Plantilla SIN claves reales
├── .gitignore
├── tests/test_logica.py   # Pruebas locales sin servicios externos
└── README.md
```

## 8. Ejecutar pruebas automatizadas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las pruebas automatizadas utilizan *mocks* y no modifican las bases de datos de Clever Cloud ni Atlas. Además, realiza las pruebas manuales anteriores para validar tu entorno real.

## 9. Errores frecuentes

- **`TemplateNotFound: perfil.html`:** el archivo correcto es `templates/perfil.html` (singular).
- **`ModuleNotFoundError`:** instala los paquetes con `pip install -r requirements.txt` dentro de `.venv`.
- **`RuntimeError: Configura SECRET_KEY`:** revisa `.env` y pega una clave aleatoria de 64 caracteres hexadecimales.
- **Error de MongoDB:** revisa `Network Access`, credenciales de usuario, URL y permisos `readWrite` en `sistema_auth`.
- **Error de MySQL:** revisa host, puerto, contraseña y nombre de base de datos en `.env`.
- **`CSRF token missing` / 400:** abre el formulario desde la aplicación, no envíes POST sin el campo oculto de CSRF.
- **`429 Too Many Requests`:** espera al menos un minuto después de muchos intentos de login/registro.
- **Rol admin:** se crea desde la terminal con el comando indicado, no mediante el formulario de registro.

## Consideraciones de seguridad y alcance

- Contraseñas guardadas como **hash bcrypt con salt**, consultas MySQL parametrizadas y rol `usuario` por defecto.
- Sesiones con cookies `HttpOnly`, `SameSite=Lax`, clave secreta y cierre de sesión por POST con CSRF.
- Límite de intentos de login por IP (almacenamiento en memoria durante el desarrollo).
- Los eventos de actividad se guardan en MongoDB; los logs no almacenan contraseñas.
- El código implementa compensación básica ante errores al escribir en ambas bases, pero **no es una transacción atómica distribuida**. En sistemas reales convendrían colas o reconciliación de estados.
- Para producción se requieren HTTPS, TLS validado hacia las bases de datos, un backend persistente para rate limiting (como Redis), pruebas de integración y monitoreo.

**Proyecto académico:** no se incluyen datos personales, contraseñas, respaldos de bases de datos, evidencias inventadas ni credenciales.
