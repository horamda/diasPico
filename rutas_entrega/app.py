"""App mínima para correr el módulo solo (desarrollo o deploy independiente en Railway).
Para sumarlo a otra app no hace falta este archivo: ver README."""
import os
from dotenv import load_dotenv
from flask import Flask, redirect

from rutas import init_rutas

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
init_rutas(app)


@app.get("/")
def index():
    return redirect("/rutas/")


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
