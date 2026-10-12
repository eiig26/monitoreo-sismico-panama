
import os
import json
import hashlib
import requests

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sismos import obtener_sismos

URL = (
    "https://services3.arcgis.com/qs4jD0lz1PLIWjKj/"
    "arcgis/rest/services/Sismos_Panama_IGC/FeatureServer/0"
)

CLIENT_ID = os.environ["ARCGIS_CLIENT_ID"]
CLIENT_SECRET = os.environ["ARCGIS_CLIENT_SECRET"]

# Primera prueba: máximo 5 sismos
LIMITE = 5


def peticion(url, datos):
    respuesta = requests.post(url, data=datos, timeout=30)
    respuesta.raise_for_status()
    resultado = respuesta.json()

    if "error" in resultado:
        raise RuntimeError(resultado["error"])

    return resultado


def obtener_token():
    resultado = peticion(
        "https://www.arcgis.com/sharing/rest/oauth2/token",
        {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
            "f": "json"
        }
    )
    return resultado["access_token"]


def id_temporal(sismo):
    # ID provisional basado en fecha y hora local
    clave = f"{sismo['fecha']}|{sismo['hora']}"
    return hashlib.sha256(clave.encode()).hexdigest()[:32]


def preparar_entidad(sismo):
    fecha_texto = f"{sismo['fecha']} {sismo['hora']}"

    fecha_local = datetime.strptime(
        fecha_texto, "%Y-%m-%d %I:%M:%S%p"
    ).replace(tzinfo=ZoneInfo("America/Panama"))

    fecha_ms = int(fecha_local.timestamp() * 1000)
    ahora_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    return {
        "attributes": {
            "id_evento": id_temporal(sismo),
            "fecha_hora": fecha_ms,
            "fecha_local": sismo["fecha"],
            "hora_local": sismo["hora"],
            "magnitud": sismo["magnitud"],
            "profundidad_km": sismo["profundidad_km"],
            "estado": sismo["estado"],
            "region": sismo["region"],
            "latitud": sismo["latitud"],
            "longitud": sismo["longitud"],
            "fecha_actualizacion": ahora_ms
        },
        "geometry": {
            "x": sismo["longitud"],
            "y": sismo["latitud"],
            "spatialReference": {"wkid": 4326}
        }
    }


def sincronizar():
    print("Iniciando prueba de sincronización...")

    token = obtener_token()
    sismos = obtener_sismos()[:LIMITE]

    # Comprobar estructura de la capa
    capa = peticion(URL, {"f": "json", "token": token})

    campos = {campo["name"] for campo in capa["fields"]}

    entidades = [preparar_entidad(s) for s in sismos]

    requeridos = set(entidades[0]["attributes"])
    faltantes = requeridos - campos

    if faltantes:
        raise RuntimeError(
            f"Faltan campos en ArcGIS: {sorted(faltantes)}"
        )

    # Consultar si los eventos ya existen
    ids = [e["attributes"]["id_evento"] for e in entidades]
    lista_ids = ",".join(f"'{valor}'" for valor in ids)

    resultado = peticion(
        f"{URL}/query",
        {
            "where": f"id_evento IN ({lista_ids})",
            "outFields": "id_evento",
            "returnGeometry": "false",
            "f": "json",
            "token": token
        }
    )

    existentes = {
        f["attributes"]["id_evento"]
        for f in resultado["features"]
    }

    nuevos = [
        e for e in entidades
        if e["attributes"]["id_evento"] not in existentes
    ]

    print("Eventos examinados:", len(entidades))
    print("Eventos ya existentes:", len(entidades) - len(nuevos))
    print("Eventos nuevos:", len(nuevos))

    if not nuevos:
        print("No hay nuevos eventos para insertar.")
        return

    resultado = peticion(
        f"{URL}/addFeatures",
        {
            "features": json.dumps(nuevos, ensure_ascii=False),
            "f": "json",
            "token": token
        }
    )

    errores = [
        r for r in resultado.get("addResults", [])
        if not r.get("success")
    ]

    if errores:
        raise RuntimeError(f"Errores al insertar: {errores}")

    if len(resultado.get("addResults", [])) != len(nuevos):
        raise RuntimeError("Respuesta de inserción incompleta.")

    print("Sismos insertados:", len(nuevos))
    print("Sincronización finalizada correctamente.")


if __name__ == "__main__":
    sincronizar()
