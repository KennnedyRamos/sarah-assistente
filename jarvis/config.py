"""Configuração central. Lê variáveis de ambiente e, se existir, o arquivo .env da raiz."""
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":  # CHAVE="valor" também vale
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


if not os.getenv("JARVIS_NO_DOTENV"):  # os testes usam só os padrões, não o .env do usuário
    _load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("JARVIS_DATA_DIR", ROOT / "data"))
MODELS_DIR = Path(os.getenv("JARVIS_MODELS_DIR", DATA_DIR / "models"))  # modelos de voz
HOST = "127.0.0.1"  # nunca escuta em outras interfaces; acesso remoto só via tailscale serve
PORT = int(os.getenv("JARVIS_PORT", "8765"))
LLM_URL = os.getenv("JARVIS_LLM_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.getenv("JARVIS_MODEL", "qwen3.5:4b")
NUM_CTX = int(os.getenv("JARVIS_NUM_CTX", "16384"))  # medido: 3,4 GB de VRAM com 8K, 3,9 GB com 24K
KEEP_ALIVE = os.getenv("JARVIS_KEEP_ALIVE", "30m")
# Amostragem recomendada pela Qwen para respostas sem "pensamento". O padrão do Ollama para o qwen3.5 é 1.0,
# que é a recomendação para o modo com pensamento e inventa mais.
TEMPERATURE = float(os.getenv("JARVIS_TEMPERATURE", "0.7"))
HISTORY_MESSAGES = int(os.getenv("JARVIS_HISTORY_MESSAGES", "20"))
SESSION_HOURS = float(os.getenv("JARVIS_SESSION_HOURS", "12"))
WHISPER_MODEL = os.getenv("JARVIS_WHISPER_MODEL", "small")
# Sessões remotas (celular) só usam ferramentas de leitura, a menos que isto seja "true".
REMOTE_TOOLS_ALL = os.getenv("JARVIS_REMOTE_TOOLS_ALL", "false").lower() == "true"
# Internet: chave gratuita da Tavily (1.000 buscas/mês, sem cartão). Sem ela, a busca usa só a Wikipédia.
TAVILY_KEY = os.getenv("JARVIS_TAVILY_KEY", "").strip()
# Contato (e-mail ou site) no identificador do programa: a Wikipédia recusa acessos sem ele.
WEB_CONTACT = os.getenv("JARVIS_WEB_CONTACT", "").strip()
# Endereço a partir das coordenadas (Google Geocoding). Sem a chave, só coordenadas + link do Google Maps.
MAPS_KEY = os.getenv("JARVIS_GOOGLE_MAPS_KEY", "").strip()
# Reconhecimento facial opcional (on/off). Desligado por padrão.
FACE_ENABLED = os.getenv("JARVIS_FACE", "off").lower() == "on"
CAMERA_INDEX = int(os.getenv("JARVIS_CAMERA", "0"))
# Usar a câmera do PC (reconhecer, cadastrar, tirar foto) a partir do celular. Desligado por padrão.
REMOTE_CAMERA = os.getenv("JARVIS_REMOTE_CAMERA", "false").lower() == "true"
# Escuta local opcional: off | palavra | palmas | ambos. Desligada por padrão.
WAKE_MODE = os.getenv("JARVIS_WAKE", "off")
CLAP_MIN_PEAK = float(os.getenv("JARVIS_CLAP_MIN_PEAK", "0.2"))
# Microfone da escuta local: número ou parte do nome (ex.: "High Definition"); vazio = padrão do Windows.
WAKE_DEVICE = os.getenv("JARVIS_WAKE_DEVICE", "").strip() or None
# Hostnames aceitos no cabeçalho Host/Origin (proteção contra DNS rebinding e CSRF).
ALLOWED_HOSTS = {"127.0.0.1", "localhost"} | {
    h.strip().lower() for h in os.getenv("JARVIS_ALLOWED_HOSTS", "").split(",") if h.strip()
}


def validate() -> list[str]:
    """Retorna a lista de erros de configuração; vazia quando está tudo certo."""
    errors = []
    if "cloud" in MODEL.lower():
        errors.append(f"JARVIS_MODEL='{MODEL}' é um modelo de nuvem; use um modelo local.")
    if urlparse(LLM_URL).hostname not in ("127.0.0.1", "localhost", "::1"):
        errors.append(f"JARVIS_LLM_URL='{LLM_URL}' não é local; a Sarah só usa inferência no próprio PC.")
    if not 1024 <= PORT <= 65535:
        errors.append(f"JARVIS_PORT={PORT} fora do intervalo 1024-65535.")
    if WAKE_MODE not in ("off", "palavra", "palmas", "ambos"):
        errors.append(f"JARVIS_WAKE='{WAKE_MODE}' inválido; use off, palavra, palmas ou ambos.")
    if NUM_CTX < 2048:
        errors.append(f"JARVIS_NUM_CTX={NUM_CTX} é pequeno demais (mínimo 2048).")
    return errors
