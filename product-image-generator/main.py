#!/usr/bin/env python3
"""
Generador de imágenes de producto - Free Tier Google AI Studio
Modelo: gemini-2.5-flash | Límite: 10 RPM | Costo: $0
"""
import asyncio
import aiohttp
import io
import csv
import os
import re
import ssl
import base64
import logging
import unicodedata
import sys
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from tqdm import tqdm
from PIL import Image

# SSL compatible con macOS, Windows y Linux
try:
    import certifi
    _SSL_CTX: Optional[ssl.SSLContext] = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = None  # usa el contexto por defecto del sistema

load_dotenv()

API_KEY        = os.getenv("GEMINI_API_KEY", "")
OUTPUT_DIR     = Path(os.getenv("OUTPUT_DIR", "output"))
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "5"))
PRODUCT_DESC   = os.getenv("PRODUCT_DESCRIPTION", "product")
VARIATIONS_CSV = os.getenv("VARIATIONS_FILE", "variaciones.csv")

MODEL     = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-image")
API_URL   = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
# Nota: MODEL se evalúa en tiempo de carga, después de load_dotenv()
RPM_DELAY = 6.0   # 60s / 10 RPM = 6s mínimo entre requests
RETRY_429 = 60    # segundos a esperar tras recibir 429

logging.basicConfig(
    filename="errors.log",
    level=logging.ERROR,
    format="%(asctime)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ── Utilidades ────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower().strip())
    return re.sub(r"[\s_]+", "-", text).strip("-")


def load_csv(path: str) -> List[Dict]:
    p = Path(path)
    if not p.exists():
        print(f"Error: '{path}' no encontrado.")
        sys.exit(1)
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"Error: '{path}' está vacío.")
        sys.exit(1)
    return rows


def build_filename(idx: int, row: Dict) -> str:
    return f"producto_{idx:03d}_{slugify(row['fondo'])}_{slugify(row['angulo'])}.jpg"


def build_prompt(row: Dict) -> str:
    return (
        f"Professional e-commerce product photo. "
        f"Product: {PRODUCT_DESC}. "
        f"Background: {row['fondo']}. "
        f"Angle: {row['angulo']}. "
        f"Lighting: {row['iluminacion']}. "
        f"High resolution, no text, no watermarks. "
        f"IMPORTANT: Do not change product color, shape, logo or labels."
    )


def decode_and_save_jpg(data: bytes, path: Path) -> None:
    with Image.open(io.BytesIO(data)) as img:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(path, "JPEG", quality=95, optimize=True)


# ── Rate limiter (10 RPM → 1 request cada 6 segundos) ────────────────────────

class RateLimiter:
    def __init__(self, interval: float = RPM_DELAY):
        self._interval = interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            gap = self._interval - (now - self._last)
            if gap > 0:
                await asyncio.sleep(gap)
            self._last = asyncio.get_event_loop().time()


# ── Llamada a la API ──────────────────────────────────────────────────────────

async def call_api(session: aiohttp.ClientSession, prompt: str) -> bytes:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    kwargs = {"ssl": _SSL_CTX} if _SSL_CTX else {}
    async with session.post(
        API_URL,
        json=payload,
        params={"key": API_KEY},
        timeout=aiohttp.ClientTimeout(total=120),
        **kwargs,
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise aiohttp.ClientResponseError(
                resp.request_info, resp.history,
                status=resp.status,
                message=body.replace(API_KEY, "***")[:400],
            )
        data = await resp.json()

    # La imagen puede aparecer en cualquier parte de la respuesta
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        if "inlineData" in part:
            return base64.b64decode(part["inlineData"]["data"])

    raise ValueError("La respuesta no contiene imagen (inlineData ausente)")


# ── Tarea por imagen ──────────────────────────────────────────────────────────

async def generate_one(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    rate: RateLimiter,
    idx: int,
    row: Dict,
    pbar: tqdm,
) -> Dict:
    filename = build_filename(idx, row)
    out_path = OUTPUT_DIR / filename

    if out_path.exists():
        pbar.update(1)
        return {"status": "skipped", "file": filename}

    prompt = build_prompt(row)
    max_retries = 3

    for attempt in range(max_retries):
        try:
            async with semaphore:
                await rate.wait()                           # ← respeta 10 RPM
                img_bytes = await call_api(session, prompt)

            decode_and_save_jpg(img_bytes, out_path)
            pbar.update(1)
            return {"status": "ok", "file": filename}

        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                # Distinguir RPM (reintentar) vs RPD (cuota diaria agotada)
                daily = "daily" in e.message.lower() or "day" in e.message.lower()
                if daily:
                    msg = "Cuota DIARIA agotada (500 RPD). Reinicia mañana o usa otra API key."
                    logging.error(f"[{filename}] HTTP 429 cuota diaria: {e.message[:200]}")
                    pbar.write(f"\n  [!] {msg}")
                    pbar.update(1)
                    return {"status": "error", "file": filename, "error": "daily quota"}
                if attempt < max_retries - 1:
                    pbar.write(f"  [429] Rate limit. Esperando {RETRY_429}s... ({filename})")
                    await asyncio.sleep(RETRY_429)
                else:
                    logging.error(f"[{filename}] HTTP 429 tras {max_retries} intentos: {e.message[:200]}")
            elif e.status >= 500:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logging.error(f"[{filename}] HTTP {e.status}: {e.message}")
            else:
                # Error 4xx que no es 429: no tiene sentido reintentar
                logging.error(f"[{filename}] HTTP {e.status}: {e.message}")
                pbar.update(1)
                return {"status": "error", "file": filename, "error": f"HTTP {e.status}"}

        except ValueError as e:
            # Respuesta sin imagen
            logging.error(f"[{filename}] {e}")
            pbar.write(f"  [!] Sin imagen en respuesta → {filename}")
            pbar.update(1)
            return {"status": "error", "file": filename, "error": str(e)}

        except Exception as e:
            safe = str(e).replace(API_KEY, "***")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                logging.error(f"[{filename}] {safe}")

    pbar.update(1)
    return {"status": "error", "file": filename, "error": "max reintentos agotados"}


# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    if not API_KEY or API_KEY.startswith("tu_api"):
        print("Error: configura GEMINI_API_KEY en el archivo .env")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_csv(VARIATIONS_CSV)
    total = len(rows)

    # Tiempo estimado: total × 6s (rate limit), con concurrencia no necesariamente lineal
    est_min = (total * RPM_DELAY) / 60
    print(f"\nGenerador de Imágenes — Free Tier Google AI Studio")
    print(f"  Imágenes    : {total}")
    print(f"  Modelo      : {MODEL}")
    print(f"  Concurrencia: {MAX_CONCURRENT}  |  Rate limit: {int(60/RPM_DELAY)} RPM")
    print(f"  Tiempo est. : ~{est_min:.1f} min")
    print(f"  Output      : {OUTPUT_DIR.resolve()}\n")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    rate = RateLimiter(RPM_DELAY)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT + 2)

    async with aiohttp.ClientSession(connector=connector) as session:
        with tqdm(total=total, desc="Generando", unit="img", colour="cyan", dynamic_ncols=True) as pbar:
            tasks = [
                generate_one(session, semaphore, rate, i + 1, row, pbar)
                for i, row in enumerate(rows)
            ]
            results = await asyncio.gather(*tasks)

    ok      = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors  = sum(1 for r in results if r["status"] == "error")

    print(f"\n{'─'*42}")
    print(f"  Generadas  : {ok}")
    print(f"  Omitidas   : {skipped}  (ya existían, no se cobran)")
    print(f"  Errores    : {errors}")
    if errors:
        print(f"  Ver detalle: errors.log")
    print(f"{'─'*42}\n")


if __name__ == "__main__":
    asyncio.run(main())
