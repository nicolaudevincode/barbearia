"""
Ponto de entrada na Vercel.

A Vercel detecta os arquivos em /api como funções serverless (Python).
Todo tráfego cai aqui; o Flask decide a rota normalmente.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app  # noqa: F401  (a Vercel usa a variável `app`)