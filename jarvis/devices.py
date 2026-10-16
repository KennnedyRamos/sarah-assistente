"""Ferramentas que pedem algo a um aparelho com a página da Sarah aberta: localização, câmeras ao vivo e foto para análise.

O pedido vai pelo WebSocket da página (celular ou PC). Localização: Geolocation do navegador (GPS/Wi-Fi), com
permissão pedida pelo próprio navegador na primeira vez. Endereço: Google Geocoding, só se houver
JARVIS_GOOGLE_MAPS_KEY. Sem a chave, coordenadas e um link do Google Maps (gratuito, sem API).
"""
import asyncio
import base64

import httpx

from . import camera, config, db, vision
from .face import DARK, brighten, camera_allowed
from .tools import ToolError, _str, tool

DEVICES = ["este", "celular", "pc"]
SNAPSHOT_MAX = 3_000_000  # foto do celular (JPEG): bem acima dos ~150 KB de uma foto de 1024 px


async def reverse_geocode(lat: float, lon: float) -> str:
    if not config.MAPS_KEY:
        return ""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://maps.googleapis.com/maps/api/geocode/json",
                             params={"latlng": f"{lat},{lon}", "key": config.MAPS_KEY, "language": "pt-BR"})
    data = r.json()
    if data.get("status") == "OK" and data.get("results"):
        return data["results"][0]["formatted_address"]
    if data.get("status") in ("REQUEST_DENIED", "OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT"):
        raise ToolError(f"O Google Maps recusou o endereço ({data['status']}): {data.get('error_message', '')}")
    return ""


def _who(target: str) -> str:
    return {"este": "deste aparelho", "celular": "do celular", "pc": "do PC"}[target]


@tool("minha_localizacao", "Localização", "Descobre onde está o aparelho (celular ou PC) que tem a página da Sarah "
      "aberta e devolve o endereço aproximado.", "leitura",
      {"aparelho": _str("este (quem está conversando, padrão), celular ou pc", enum=DEVICES)})
async def minha_localizacao(args, ctx):
    if not ctx.device:
        raise ToolError("A localização só funciona pela conversa na página da Sarah.")
    target = args.get("aparelho") or "este"
    data = await ctx.device(target, "geo")
    try:
        lat, lon, acc = float(data["lat"]), float(data["lon"]), float(data.get("accuracy") or 0)
    except (KeyError, TypeError, ValueError):
        raise ToolError("O aparelho mandou uma localização inválida.") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ToolError("O aparelho mandou uma localização inválida.")
    try:
        address = await reverse_geocode(lat, lon)
    except (httpx.HTTPError, ValueError):  # sem endereço, a resposta segue só com as coordenadas
        address = ""
    db.audit(ctx.actor, "localizacao_consultada", {"aparelho": target})
    maps = f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"
    if address:
        return f"Localização {_who(target)}: {address} (precisão de ~{acc:.0f} m) | mapa: {maps}"
    # medido: sem endereço, o modelo de 4B "adivinhou" outra cidade a partir das coordenadas
    return (f"Localização {_who(target)}: endereço indisponível{'' if config.MAPS_KEY else ' (sem JARVIS_GOOGLE_MAPS_KEY)'}. "
            f"Coordenadas {lat:.5f}, {lon:.5f} (precisão de ~{acc:.0f} m). Mapa: {maps}\n"
            "IMPORTANTE: NÃO diga cidade, bairro ou estado — não dá para saber só pelas coordenadas. "
            "Responda apenas com as coordenadas e o link do mapa.")


@tool("mostrar_camera", "Câmera ao vivo", "Mostra AO VIVO a câmera do PC ou do celular na tela de quem pediu "
      "(desliga sozinha em 10 minutos).", "leitura", {"origem": _str("pc ou celular", enum=["pc", "celular"])},
      ("origem",))
async def mostrar_camera(args, ctx):
    origem = args["origem"]
    if origem == "pc":
        camera_allowed(ctx.remote)
        if not camera.opencv_available():
            raise ToolError("Falta o OpenCV para ler a webcam do PC: rode iniciar.bat para instalar as dependências.")
    else:
        if not ctx.device:
            raise ToolError("A câmera do celular só funciona pela conversa na página da Sarah.")
        await ctx.device("celular", "camera_start")
    db.audit(ctx.actor, "camera_ao_vivo", {"origem": origem})
    return (f"Câmera {'do PC' if origem == 'pc' else 'do celular'} ao vivo [camera:{origem}]. "
            "Ela desliga sozinha em 10 minutos ou no botão Parar.")


@tool("olhar_camera", "Olhar pela câmera", "Tira uma foto da câmera do PC ou do celular e responde o que dá para ver nela "
      "(objetos, ambiente, textos, o que a pessoa segura). Para saber QUEM é a pessoa, use quem_esta_na_camera.", "leitura",
      {"origem": _str("pc ou celular", enum=["pc", "celular"]), "pergunta": _str("O que observar (opcional)")},
      ("origem",), timeout=90)
async def olhar_camera(args, ctx):
    origem = args["origem"]
    if origem == "pc":
        camera_allowed(ctx.remote)
        if not camera.opencv_available():
            raise ToolError("Falta o OpenCV para ler a webcam do PC: rode iniciar.bat para instalar as dependências.")
        try:
            img = (await asyncio.to_thread(camera.pc_frames, 1))[0]
        except camera.CameraError as e:
            raise ToolError(str(e)) from None
        if img.mean() < DARK:  # webcam no escuro: clarear ajuda o modelo a enxergar
            img = brighten(img)
    else:
        if not ctx.device:
            raise ToolError("A câmera do celular só funciona pela conversa na página da Sarah.")
        data = await ctx.device("celular", "camera_snapshot")  # o celular avisa na tela que tirou a foto
        try:
            raw = base64.b64decode(str(data.get("jpeg", "")), validate=True)
        except ValueError:
            raw = b""
        if not raw or len(raw) > SNAPSHOT_MAX:
            raise ToolError("O celular mandou uma foto inválida.")
        img = vision.decode(raw)
    answer = await vision.describe(vision.encode(img), (args.get("pergunta") or "Descreva o que aparece nesta imagem.")[:500])
    db.audit(ctx.actor, "camera_olhada", {"origem": origem})
    return f"Análise da foto da câmera {'do PC' if origem == 'pc' else 'do celular'} (a foto não foi salva): {answer}"

