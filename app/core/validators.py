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

def calcular_dv_nit(nit: str) -> str:
    """Calcula el digito de verificacion de un NIT colombiano (algoritmo modulo 11)."""
    pesos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    nit_invertido = nit[::-1]
    total = sum(int(d) * pesos[i] for i, d in enumerate(nit_invertido))
    residuo = total % 11
    if residuo in (0, 1):
        return str(residuo)
    return str(11 - residuo)

Documento = Annotated[str, AfterValidator(_documento)]
Telefono = Annotated[str, AfterValidator(_telefono)]
PasswordSegura = Annotated[str, AfterValidator(_password)]