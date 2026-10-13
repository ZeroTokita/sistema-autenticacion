// Ejecutar con mongosh conectado a MongoDB Atlas.
const database = db.getSiblingDB("sistema_auth");
if (!database.getCollectionNames().includes("perfiles")) {
    database.createCollection("perfiles");
}
if (!database.getCollectionNames().includes("logs")) {
    database.createCollection("logs");
}
database.perfiles.createIndex({ usuario_id: 1 }, { unique: true });
database.logs.createIndex({ fecha: -1 });
print("Colecciones e índices listos.");
