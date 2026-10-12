
import os
import requests

# Configuración
CLIENT_ID = os.environ["ARCGIS_CLIENT_ID"]
CLIENT_SECRET = os.environ["ARCGIS_CLIENT_SECRET"]

FEATURE_LAYER_URL = (
    "https://services3.arcgis.com/qs4jD0lz1PLIWjKj/"
    "arcgis/rest/services/Sismos_Panama_IGC/FeatureServer/0"
)

# 1. Obtener token OAuth 2.0
print("1. Solicitando autenticación con ArcGIS Online...")

token_url = "https://www.arcgis.com/sharing/rest/oauth2/token"

response = requests.post(
    token_url,
    data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
        "f": "json"
    },
    timeout=30
)

response.raise_for_status()
token_data = response.json()

if "error" in token_data:
    raise RuntimeError(
        f"Error de autenticación: {token_data['error'].get('message')}"
    )

access_token = token_data["access_token"]
print("Autenticación exitosa.")

# 2. Consultar Feature Layer
print("2. Consultando Feature Layer...")

response = requests.post(
    f"{FEATURE_LAYER_URL}/query",
    data={
        "where": "1=1",
        "returnCountOnly": "true",
        "f": "json",
        "token": access_token
    },
    timeout=30
)

response.raise_for_status()
resultado = response.json()

if "error" in resultado:
    raise RuntimeError(
        f"Error consultando capa: {resultado['error'].get('message')}"
    )

print("Conexión exitosa con ArcGIS Online.")
print("Feature Layer: Sismos_Panama_IGC")
print("Total de entidades:", resultado["count"])
print("Prueba finalizada correctamente.")
