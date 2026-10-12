
import requests
from bs4 import BeautifulSoup
from datetime import datetime

URL = "https://sismosgeociencias.up.ac.pa/"

def obtener_sismos():
    response = requests.get(URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # El HTML incluye tablas para distintos tamaños de pantalla.
    # Usamos la tabla principal (escritorio).
    tabla = soup.select_one("table.w3-table")

    if tabla is None:
        raise ValueError("No se encontró la tabla de sismos.")

    sismos = []

    for fila in tabla.select("tr"):
        celdas = fila.find_all("td")

        if len(celdas) != 9:
            continue

        sismo = {
            "estado": celdas[0].get_text(strip=True),
            "fecha": celdas[1].get_text(strip=True),
            "hora": celdas[2].get_text(strip=True),
            "latitud": float(celdas[3].get_text(strip=True)),
            "longitud": float(celdas[4].get_text(strip=True)),
            "profundidad_km": float(
                celdas[5].get_text(strip=True).replace("km", "")
            ),
            "magnitud": float(celdas[6].get_text(strip=True)),
            "region": celdas[7].get_text(strip=True),
        }

        sismos.append(sismo)

    return sismos


if __name__ == "__main__":
    sismos = obtener_sismos()

    print("MONITOREO SISMICO DE PANAMA")
    print("Fecha de consulta:", datetime.now().isoformat())
    print("Total de sismos encontrados:", len(sismos))

    for sismo in sismos[:5]:
        print(sismo)

    if not sismos:
        raise RuntimeError("La consulta no devolvió sismos.")
