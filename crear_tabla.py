
import os
import mysql.connector
from dotenv import load_dotenv

# Cargar variables del archivo .env
load_dotenv()

conexion = None
cursor = None

try:
    # Conectar con MySQL en Clever Cloud
    conexion = mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ["MYSQL_PORT"]),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        connection_timeout=10
    )

    print("Conexión a MySQL exitosa")

    cursor = conexion.cursor()

    # Leer el archivo SQL
    with open("schema.sql", "r", encoding="utf-8") as archivo:
        consulta_sql = archivo.read()

    # Crear tabla
    cursor.execute(consulta_sql)
    conexion.commit()

    print("Tabla usuarios creada o ya existente.")

    # Verificar existencia de la tabla
    cursor.execute("SHOW TABLES LIKE 'usuarios'")

    if cursor.fetchone():
        print("Verificación: tabla usuarios encontrada.")

        # Mostrar las columnas
        cursor.execute("DESCRIBE usuarios")

        print("\nColumnas de la tabla:")

        for columna in cursor.fetchall():
            print(
                f"- {columna[0]} | "
                f"Tipo: {columna[1]} | "
                f"Clave: {columna[3]}"
            )

        # Mostrar índices de la tabla
        cursor.execute("SHOW INDEX FROM usuarios")

        print("\nÍndices:")
        for indice in cursor.fetchall():
            print(f"- {indice[2]}")

    else:
        print("No se encontró la tabla usuarios.")

except mysql.connector.Error as error:
    print("Error de MySQL:", error)

except (OSError, KeyError, ValueError) as error:
    print("Error de configuración:", error)

finally:
    if cursor is not None:
        cursor.close()

    if conexion is not None and conexion.is_connected():
        conexion.close()
        print("\nConexión cerrada correctamente.")
