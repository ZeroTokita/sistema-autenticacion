
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

uri = os.getenv("MONGO_URI")
nombre_db = os.getenv("MONGO_DB", "sistema_auth")

if not uri:
    raise RuntimeError("Falta MONGO_URI en .env")

cliente = MongoClient(uri, serverSelectionTimeoutMS=8000)

try:
    cliente.admin.command("ping")
    print("Conexión a MongoDB Atlas exitosa")

    db = cliente[nombre_db]
    colecciones = db.list_collection_names()

    print("Base de datos:", db.name)
    print("Colecciones:", colecciones)

    for nombre in ("perfiles", "logs"):
        if nombre in colecciones:
            print(f"{nombre}: encontrada")
        else:
            print(f"{nombre}: no encontrada")

except Exception as error:
    print("Error de conexión:")
    print(error)

finally:
    cliente.close()
