import io
import os
import time
import base64
import tracemalloc
import gc

import streamlit as st
import psutil
from PIL import Image


# ----------------------------
# Medición
# ----------------------------
def rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def ms() -> float:
    return time.perf_counter() * 1000


def stage(rows, name, t0, rss0):
    rows.append(
        {
            "etapa": name,
            "ms": round(ms() - t0, 1),
            "rss_mb": round(rss_mb(), 1),
            "delta_mb": round(rss_mb() - rss0, 1),
        }
    )


# ----------------------------
# Funciones “tipo app”
# ----------------------------
def normalize_to_jpeg_bytes(file_bytes: bytes, max_side=800, quality=60) -> bytes:
    # PIL abre imagen HD (pico de RAM aquí)
    img = Image.open(io.BytesIO(file_bytes))
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


def html_from_pil_images(pil_images, max_side=800, quality=60) -> str:
    """
    Simula html_generator actual:
    - recibe PIL Images
    - copia/reescala/guarda jpeg
    - base64
    """
    parts = []
    for img in pil_images:
        im = img.copy()
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(out.getvalue()).decode("ascii")
        parts.append(f"<img style='max-width:320px;margin:6px' src='data:image/jpeg;base64,{b64}' />")
    return "<html><body>" + "\n".join(parts) + "</body></html>"


def html_from_jpeg_bytes(jpeg_list) -> str:
    """Optimizado: base64 directo, sin PIL."""
    parts = []
    for b in jpeg_list:
        b64 = base64.b64encode(b).decode("ascii")
        parts.append(f"<img style='max-width:320px;margin:6px' src='data:image/jpeg;base64,{b64}' />")
    return "<html><body>" + "\n".join(parts) + "</body></html>"


def open_jpegs_as_pil(jpeg_list):
    """Simula tu _state_to_pil_images(): reabre bytes ya normalizados (otra pasada PIL)."""
    out = []
    for b in jpeg_list:
        out.append(Image.open(io.BytesIO(b)))
    return out


# ----------------------------
# UI
# ----------------------------
st.set_page_config(page_title="Bench RAM v2 (doble PIL vs optimizado)", layout="wide")
st.title("Bench RAM v2 — Simulación app vs optimizado")

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    uploads = st.file_uploader(
        "Sube las mismas 5 fotos HD (JPG/PNG/WEBP).",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
    )

    max_photos = st.number_input("Máximo de fotos", 1, 30, 5, 1)
    max_side = st.number_input("Max side (px)", 200, 3000, 800, 50)
    quality = st.number_input("Calidad JPEG", 30, 95, 60, 1)

    do_gc = st.checkbox("Forzar gc.collect() entre fases (solo para ver tendencia)", value=False)
    run = st.button("Ejecutar bench", type="primary")

with col2:
    st.caption("RSS = RAM real del proceso. Se comparan dos pipelines con las mismas fotos.")


def maybe_gc():
    if do_gc:
        gc.collect()


if run:
    if not uploads:
        st.error("Sube al menos 1 foto.")
        st.stop()

    sel = uploads[: int(max_photos)]

    # Leer raw bytes
    raw = [f.getvalue() for f in sel]
    raw_total = sum(len(b) for b in raw)

    # ==========================================================
    # PIPELINE A: “como la app” (doble PIL)
    # 1) PIL para normalizar a jpeg_bytes
    # 2) PIL otra vez: reabrir esos jpeg_bytes para el HTML
    # 3) HTML re-encode a jpeg + base64 (tipo html_generator)
    # ==========================================================
    tracemalloc.start()
    rss0_a = rss_mb()
    t0 = ms()
    rows_a = []
    stage(rows_a, "A: inicio", t0, rss0_a)

    t = ms()
    jpeg_bytes_a = [normalize_to_jpeg_bytes(b, int(max_side), int(quality)) for b in raw]
    stage(rows_a, "A: normalizar (PIL) -> jpeg_bytes", t, rss0_a)
    maybe_gc()

    t = ms()
    pil_imgs_a = open_jpegs_as_pil(jpeg_bytes_a)  # segunda pasada por PIL
    stage(rows_a, "A: reabrir jpeg_bytes como PIL (2ª pasada)", t, rss0_a)
    maybe_gc()

    t = ms()
    html_a = html_from_pil_images(pil_imgs_a, int(max_side), int(quality))  # re-encode + b64
    stage(rows_a, "A: generar HTML desde PIL (re-encode+b64)", t, rss0_a)

    cur_a, peak_a = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    norm_total_a = sum(len(b) for b in jpeg_bytes_a)

    # Limpieza de refs grandes (para que B no herede tanto)
    del pil_imgs_a
    del html_a
    maybe_gc()

    # ==========================================================
    # PIPELINE B: optimizado (una sola pasada PIL + HTML sin PIL)
    # 1) PIL para normalizar a jpeg_bytes
    # 2) HTML base64 directo (sin PIL)
    # ==========================================================
    tracemalloc.start()
    rss0_b = rss_mb()
    t0b = ms()
    rows_b = []
    stage(rows_b, "B: inicio", t0b, rss0_b)

    t = ms()
    jpeg_bytes_b = [normalize_to_jpeg_bytes(b, int(max_side), int(quality)) for b in raw]
    stage(rows_b, "B: normalizar (PIL) -> jpeg_bytes", t, rss0_b)
    maybe_gc()

    t = ms()
    html_b = html_from_jpeg_bytes(jpeg_bytes_b)  # sin PIL
    stage(rows_b, "B: generar HTML desde bytes (sin PIL)", t, rss0_b)

    cur_b, peak_b = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    norm_total_b = sum(len(b) for b in jpeg_bytes_b)

    # Resultados
    with col2:
        st.markdown("## Pipeline A — como la app (doble PIL)")
        st.table(rows_a)
        st.write(
            {
                "fotos": len(sel),
                "raw_total_mb": round(raw_total / (1024 * 1024), 2),
                "normalized_total_mb": round(norm_total_a / (1024 * 1024), 2),
                "tracemalloc_current_mb": round(cur_a / (1024 * 1024), 2),
                "tracemalloc_peak_mb": round(peak_a / (1024 * 1024), 2),
                "html_len_chars": "n/a (liberado para no sesgar B)",
            }
        )

        st.markdown("## Pipeline B — optimizado (1 PIL + HTML sin PIL)")
        st.table(rows_b)
        st.write(
            {
                "fotos": len(sel),
                "raw_total_mb": round(raw_total / (1024 * 1024), 2),
                "normalized_total_mb": round(norm_total_b / (1024 * 1024), 2),
                "tracemalloc_current_mb": round(cur_b / (1024 * 1024), 2),
                "tracemalloc_peak_mb": round(peak_b / (1024 * 1024), 2),
                "html_len_chars": len(html_b),
            }
        )

        st.markdown("## Diferencia clave (picos)")
        st.write(
            {
                "A_rss_base_mb": round(rss0_a, 1),
                "B_rss_base_mb": round(rss0_b, 1),
                "nota": "Compara el delta_mb máximo de cada tabla: ahí está el ahorro real.",
            }
        )

    with col1:
        st.markdown("### Vista previa (solo B, opcional)")
        with st.expander("Ver HTML B (puede pesar)"):
            st.components.v1.html(html_b, height=400, scrolling=True)
