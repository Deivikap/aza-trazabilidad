"""Acceso a MongoDB (payload JSON crudo). Con MONGO_URI=mongomock se usa un doble en memoria para pruebas."""
from django.conf import settings

_client = None
_index_ready = False


def coleccion():
    global _client, _index_ready
    if _client is None:
        if settings.MONGO_URI == "mongomock":
            import mongomock
            _client = mongomock.MongoClient()
        else:
            import pymongo
            _client = pymongo.MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
    col = _client[settings.MONGO_DB]["mensajes_inspeccion"]
    if not _index_ready:
        col.create_index("id_externo", unique=True, name="uk_id_externo_json")
        _index_ready = True
    return col


def upsert_payload(id_externo, payload):
    coleccion().update_one({"id_externo": id_externo}, {"$set": {"id_externo": id_externo, **payload}}, upsert=True)


def obtener(id_externo):
    return coleccion().find_one({"id_externo": id_externo}, {"_id": 0})


def ids():
    return {d["id_externo"] for d in coleccion().find({}, {"id_externo": 1, "_id": 0})}


def ping():
    coleccion().database.client.admin.command("ping") if settings.MONGO_URI != "mongomock" else None


def reset_para_pruebas():
    global _client, _index_ready
    _client = None
    _index_ready = False
