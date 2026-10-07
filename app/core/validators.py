import re
from typing import Annotated

from pydantic import AfterValidator


def _solo_numeros(valor: str, campo: str, min_len: int, max_len: int) -> str:
    valor = valor.strip()
    if not re.fullmatch(r"[0-9]+", valor):
        raise ValueError(f"El {campo} solo debe contener números")
    if not (min_len <= len(valor) <= max_len):
        raise ValueError(f"El {campo} debe tener entre {min_len} y {max_len} dígitos")
    return valor


def _documento(valor: str) -> str:
    return _solo_numeros(valor, "documento", 6, 12)


def _telefono(valor: str) -> str:
    return _solo_numeros(valor, "teléfono", 10, 10)


def _password(valor: str) -> str:
    if len(valor) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    if not re.search(r"[A-Z]", valor):
        raise ValueError("La contraseña debe incluir al menos una mayúscula")
    if not re.search(r"[a-z]", valor):
        raise ValueError("La contraseña debe incluir al menos una minúscula")
    if not re.search(r"[^\w\s]|_", valor):
        raise ValueError("La contraseña debe incluir al menos un símbolo")
    return valor


Documento = Annotated[str, AfterValidator(_documento)]
Telefono = Annotated[str, AfterValidator(_telefono)]
PasswordSegura = Annotated[str, AfterValidator(_password)]