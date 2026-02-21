import io
import os
import time
import base64
import tracemalloc

import streamlit as st
import psutil
from PIL import Image

# Si quieres usar tus funciones reales, descomenta:
# import ia_engine
# import html_generator


# ----------------------------
# Helpers de medición
# ----------------------------
def rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def ms() -> float:
    return time.perf_counter() * 1000


def stage_log(rows, name, t_start_ms, rss_base):
    rows.append(
        {
            "etapa": name,
            "ms": round(ms() - t_start_ms, 1),
            "rss_mb": round(rss_mb(), 1),
            "delta_mb": round(rss_mb() - rss_base, 1),
        }
    )


# ----------------------------
# Pipeline "demo" (sin Vertex)
# ----------------------------
def normalize_to_jpeg_bytes(file_bytes: bytes, max_side=800, quality=60) -> bytes:
    """Normaliza a JPEG (similar a tu idea)."""
    img = Image.open(io.BytesIO(file_bytes))
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


def html_embed_base64(jpeg_list: list[bytes]) -> str:
    """Genera un HTML sencillo con imágenes embebidas (sin PIL extra)."""
    parts = []
    for b in jpeg_list:
        b64 = base64.b64encode(b).decode("ascii")
        parts.append(f"<img style='max-width:320px;margin:6px' src='data:image/jpeg;base64,{b64}' />")
    return "<html><body>" + "\n".join(parts) + "</body></html>"


# ----------------------------
# UI
# ----------------------------
st.set_page_config(page_title="Bench RAM fotos", layout="wide")
st.title("Bench de RAM (fotos)")

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.subheader("Entrada")
    uploads = st.file_uploader(
        "Sube 5 fotos (JPG/PNG/WEBP). Cuanto más grandes, mejor para el test.",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
    )

    max_photos = st.number_input("Máximo de fotos a procesar", min_value=1, max_value=20, value=5, step=1)
    max_side = st.number_input("Max side (px) para normalizar", min_value=200, max_value=3000, value=800, step=50)
    quality = st.number_input("Calidad JPEG", min_value=30, max_value=95, value=60, step=1)

    run = st.button("Ejecutar benchmark", type="primary")

with col2:
    st.subheader("Medición")
    st.caption("RSS = RAM real del proceso. tracemalloc = memoria Python (pico) durante la ejecución.")

if run:
    if not uploads:
        st.error("Sube al menos 1 foto.")
        st.stop()

    sel = uploads[: int(max_photos)]

    rows = []
    rss_base = rss_mb()

    tracemalloc.start()
    t0 = ms()
    stage_log(rows, "inicio", t0, rss_base)

    # 1) Leer bytes (simula 'upload' -> bytes)
    t1 = ms()
    raw_bytes = []
    total_raw = 0
    for f in sel:
        b = f.getvalue()
        raw_bytes.append(b)
        total_raw += len(b)
    stage_log(rows, "leer bytes (uploads)", t1, rss_base)

    # 2) Normalizar a JPEG optimizado
    t2 = ms()
    normalized = []
    total_norm = 0
    for b in raw_bytes:
        nb = normalize_to_jpeg_bytes(b, max_side=int(max_side), quality=int(quality))
        normalized.append(nb)
        total_norm += len(nb)
    stage_log(rows, "normalizar JPEG (PIL)", t2, rss_base)

    # 3) HTML embebiendo base64 (string grande)
    t3 = ms()
    html = html_embed_base64(normalized)
    stage_log(rows, "generar HTML (base64)", t3, rss_base)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Resultados
    with col2:
        st.markdown("### Resultados")
        st.table(rows)

        st.markdown("### Tamaños")
        st.write(
            {
                "fotos": len(sel),
                "raw_total_mb": round(total_raw / (1024 * 1024), 2),
                "normalized_total_mb": round(total_norm / (1024 * 1024), 2),
                "html_len_chars": len(html),
            }
        )

        st.markdown("### tracemalloc")
        st.write(
            {
                "current_mb": round(current / (1024 * 1024), 2),
                "peak_mb": round(peak / (1024 * 1024), 2),
            }
        )

        st.markdown("### Vista previa (opcional)")
        with st.expander("Ver HTML embebido (puede ser pesado)"):
            st.components.v1.html(html, height=400, scrolling=True)
