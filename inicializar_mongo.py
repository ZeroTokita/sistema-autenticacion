"""Crea índices en las colecciones existentes de MongoDB Atlas."""

import os
from dotenv import load_dotenv
from pymongo import MongoClient, DESCENDING

load_dotenv()
uri = os.environ["MONGO_URI"]
cliente = MongoClient(uri, serverSelectionTimeoutMS=8000)
try:
    cliente.admin.command("ping")
    base = cliente[os.getenv("MONGO_DB", "sistema_auth")]
    base["perfiles"].create_index("usuario_id", unique=True)
    base["logs"].create_index([("fecha", DESCENDING)])
    print("MongoDB: índices usuario_id (único) y fecha creados o existentes.")
except Exception as exc:
    print("No se pudieron crear los índices. Comprueba permisos y duplicados.")
    raise SystemExit(1) from exc
finally:
    cliente.close()
