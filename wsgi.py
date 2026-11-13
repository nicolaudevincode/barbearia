"""
Arquivo de entrada para servidores que usam WSGI
(PythonAnywhere, Render, Railway, Gunicorn, uWSGI...).

No computador, o mais simples é rodar:  py app.py
"""

from app import app as application  # noqa: F401