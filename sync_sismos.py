
import os
import json
import hashlib
import requests

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sismos import obtener_sismos
from collections import defaultdict

URL = (
    "https://services3.arcgis.com/qs4jD0lz1PLIWjKj/"
    "arcgis/rest/services/Sismos_Panama_IGC/FeatureServer/0"
)

CLIENT_ID = os.environ["ARCGIS_CLIENT_ID"]
CLIENT_SECRET = os.environ["ARCGIS_CLIENT_SECRET"]

LOTE = 100
CAMPOS_COMPARAR = [
    "estado", "magnitud", "profundidad_km",
    "region", "latitud", "longitud"
]


def peticion(url, datos):
    respuesta = requests.post(url, data=datos, timeout=60)
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


def generar_id(sismo):
    clave = f"{sismo['fecha']}|{sismo['hora']}"
    return hashlib.sha256(
        clave.encode("utf-8")
    ).hexdigest()[:32]


def preparar_entidad(sismo):
    fecha = datetime.strptime(
        f"{sismo['fecha']} {sismo['hora']}",
        "%Y-%m-%d %I:%M:%S%p"
    ).replace(tzinfo=ZoneInfo("America/Panama"))

    fecha_ms = int(fecha.timestamp() * 1000)
    ahora_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    return {
        "attributes": {
            "id_evento": generar_id(sismo),
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


def consultar_existentes(token, ids):
    existentes = {}

    for inicio in range(0, len(ids), LOTE):
        bloque = ids[inicio:inicio + LOTE]
        valores = ",".join(f"'{x}'" for x in bloque)

        resultado = peticion(
            f"{URL}/query",
            {
                "where": f"id_evento IN ({valores})",
                "outFields": "*",
                "returnGeometry": "false",
                "f": "json",
                "token": token
            }
        )

        for entidad in resultado.get("features", []):
            atributos = entidad["attributes"]
            identificador = atributos["id_evento"]

            if identificador in existentes:
                raise RuntimeError(
                    f"ID duplicado en ArcGIS: {identificador}"
                )

            existentes[identificador] = atributos

    return existentes


def hay_cambios(nuevo, anterior):
    for campo in CAMPOS_COMPARAR:
        a = nuevo[campo]
        b = anterior.get(campo)

        if isinstance(a, (float, int)):
            if b is None or abs(float(a) - float(b)) > 0.000001:
                return True
        elif a != b:
            return True

    return False


def aplicar_lotes(token, entidades, tipo):
    total = 0

    for inicio in range(0, len(entidades), LOTE):
        bloque = entidades[inicio:inicio + LOTE]

        parametros = {
            "f": "json",
            "token": token,
            "rollbackOnFailure": "true",
            tipo: json.dumps(bloque, ensure_ascii=False)
        }

        resultado = peticion(
            f"{URL}/applyEdits",
            parametros
        )

        campo_resultado = (
            "addResults" if tipo == "adds"
            else "updateResults"
        )

        resultados = resultado.get(campo_resultado)

        if resultados is None or len(resultados) != len(bloque):
            raise RuntimeError(
                f"Respuesta incompleta al ejecutar {tipo}"
            )

        errores = [
            r for r in resultados if not r.get("success")
        ]

        if errores:
            raise RuntimeError(
                f"Fallaron operaciones {tipo}: {errores}"
            )

        total += len(resultados)

    return total


def sincronizar():
    print("=== MONITOREO SISMICO DE PANAMA ===")

    token = obtener_token()
    sismos = obtener_sismos()

    # DIAGNÓSTICO DE DUPLICADOS
    grupos = defaultdict(list)
    
    for sismo in sismos:
        clave = f"{sismo['fecha']}|{sismo['hora']}"
        grupos[clave].append(sismo)
    
    repetidos = {
        clave: registros
        for clave, registros in grupos.items()
        if len(registros) > 1
    }
    
    print("=== DIAGNOSTICO DE DUPLICADOS ===")
    print("Total registros:", len(sismos))
    print("Fechas y horas únicas:", len(grupos))
    print("Grupos con repetidos:", len(repetidos))
    
    for clave, registros in list(repetidos.items())[:3]:
        print("Fecha y hora:", clave)
    
        for registro in registros[:3]:
            print(
                "Latitud:", registro["latitud"],
                "Longitud:", registro["longitud"],
                "Magnitud:", registro["magnitud"],
                "Estado:", registro["estado"]
            )
    
    print("=== FIN DEL DIAGNOSTICO ===")



    if not sismos:
        raise RuntimeError("La fuente no devolvió sismos.")

    capa = peticion(URL, {"f": "json", "token": token})

    campos = {c["name"] for c in capa["fields"]}
    id_objectid = capa["objectIdField"]

    entidades = {}

    for sismo in sismos:
        entidad = preparar_entidad(sismo)
        identificador = entidad["attributes"]["id_evento"]

        if identificador in entidades:
            if entidad["attributes"] != entidades[identificador]["attributes"]:
                # fecha_actualizacion varía, por eso
                # la excluimos de esta comparación
                actual = entidad["attributes"].copy()
                previo = entidades[identificador]["attributes"].copy()
                actual.pop("fecha_actualizacion", None)
                previo.pop("fecha_actualizacion", None)

                if actual != previo:
                    raise RuntimeError(
                        f"Registros distintos con mismo ID: {identificador}"
                    )

        entidades[identificador] = entidad

    requeridos = set(
        next(iter(entidades.values()))["attributes"]
    )

    if requeridos - campos:
        raise RuntimeError(
            f"Faltan campos: {sorted(requeridos - campos)}"
        )

    if not {"Create", "Update"}.issubset(
        set(capa.get("capabilities", "").split(","))
    ):
        raise RuntimeError(
            "La capa debe permitir Create y Update."
        )

    existentes = consultar_existentes(
        token, list(entidades.keys())
    )

    nuevos = []
    actualizados = []
    sin_cambios = 0

    for identificador, entidad in entidades.items():
        anterior = existentes.get(identificador)

        if anterior is None:
            nuevos.append(entidad)
        elif hay_cambios(entidad["attributes"], anterior):
            entidad["attributes"][id_objectid] = anterior[id_objectid]
            actualizados.append(entidad)
        else:
            sin_cambios += 1

    print("Eventos obtenidos:", len(sismos))
    print("Eventos únicos:", len(entidades))
    print("Nuevos:", len(nuevos))
    print("Por actualizar:", len(actualizados))
    print("Sin cambios:", sin_cambios)

    insertados = aplicar_lotes(token, nuevos, "adds")
    modificados = aplicar_lotes(token, actualizados, "updates")

    print("Insertados:", insertados)
    print("Actualizados:", modificados)
    print("Sin cambios:", sin_cambios)
    print("Sincronización finalizada correctamente.")


if __name__ == "__main__":
    sincronizar()
