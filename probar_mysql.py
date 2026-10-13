
import os
import mysql.connector
from dotenv import load_dotenv

# Cargar credenciales desde .env
load_dotenv()

conexion = None
cursor = None

try:
    # Establecer conexión con Clever Cloud
    conexion = mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ["MYSQL_PORT"]),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        connection_timeout=10
    )

    if conexion.is_connected():
        print("Conexión a MySQL exitosa")

        cursor = conexion.cursor()

        # Consultar la base de datos actual
        cursor.execute("SELECT DATABASE()")
        nombre_db = cursor.fetchone()[0]

        print("Base de datos:", nombre_db)

        # Consultar las tablas existentes
        cursor.execute("SHOW TABLES")
        tablas = cursor.fetchall()

        print("Tablas encontradas:")

        if tablas:
            for tabla in tablas:
                print("-", tabla[0])
        else:
            print("La base de datos no tiene tablas.")

except mysql.connector.Error as error:
    print("Error de conexión a MySQL:")
    print(error)

except (KeyError, ValueError) as error:
    print("Revisa la configuración del archivo .env")
    print(error)

finally:
    if cursor is not None:
        cursor.close()

    if conexion is not None and conexion.is_connected():
        conexion.close()
        print("Conexión cerrada correctamente")
