import os

from dotenv import load_dotenv

load_dotenv()  # lee el archivo .env de esta carpeta (nunca va al repositorio)


def get_secret(ref: str) -> str:
    """Entrega un secreto por su referencia. Si falta, el servicio no arranca."""
    value = os.environ.get(ref)
    if not value:
        raise RuntimeError(f"Falta el secreto {ref}")
    return value
