"""Punto de entrada para Railway.

Railway define la variable PORT. Levantamos uvicorn con la app FastAPI, que a su vez
arranca el scheduler diario (21:10 hora Colombia) y sirve las imágenes públicamente.
"""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("neurito.server:app", host="0.0.0.0", port=port, log_level="info")
