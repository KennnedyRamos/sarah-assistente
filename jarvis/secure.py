"""Cifragem local com a DPAPI do Windows: só a sua conta do Windows, neste PC, consegue decifrar."""
import ctypes
from ctypes import wintypes


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt32 = ctypes.WinDLL("crypt32")
_kernel32 = ctypes.WinDLL("kernel32")
for _fn in (_crypt32.CryptProtectData, _crypt32.CryptUnprotectData):
    _fn.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                    wintypes.DWORD, ctypes.POINTER(_Blob)]
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]


def dpapi(data: bytes, protect: bool) -> bytes:
    """Cifra (protect=True) ou decifra. Levanta ValueError se o dado não for desta conta/PC."""
    buf = ctypes.create_string_buffer(data, len(data))
    inp, out = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _Blob()
    fn = _crypt32.CryptProtectData if protect else _crypt32.CryptUnprotectData
    if not fn(ctypes.byref(inp), None, None, None, None, 0x1, ctypes.byref(out)):  # 0x1 = sem interface gráfica
        raise ValueError("Dado cifrado por outro usuário ou PC, ou corrompido.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        _kernel32.LocalFree(out.pbData)
