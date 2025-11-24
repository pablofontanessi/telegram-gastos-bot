#!/usr/bin/env python3
import os
import json
import re
import asyncio
import logging
from datetime import date

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters
)

import gspread
from google.oauth2.service_account import Credentials


# -------------------------------------------------------------------
#                       CONFIGURACIÓN Y LOGGING
# -------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")  # TOKEN desde secrets de Fly.io

# Regex para validar montos tipo "100" o "100.50"
AMOUNT_REGEX = re.compile(r"^\d+(\.\d+)?$")


# -------------------------------------------------------------------
#               CARGA DE CREDENCIALES DESDE SECRETS (Fly.io)
# -------------------------------------------------------------------

def init_gspread_from_env():
    """
    Lee GOOGLE_CREDENTIALS del entorno (Fly.io secrets),
    inicializa Credentials y devuelve gspread client autorizado.
    """
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        logger.error("GOOGLE_CREDENTIALS no encontrado en variables de entorno.")
        raise SystemExit("Falta el secreto GOOGLE_CREDENTIALS")

    creds_dict = json.loads(creds_json)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    return gc


# -------------------------------------------------------------------
#                          HANDLER PRINCIPAL
# -------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa cada mensaje de texto, valida, parsea y guarda en Google Sheets."""
    text = (update.message.text or "").strip()

    if not text:
        await update.message.reply_text(
            "Mensaje vacío. Usa: descripcion monto [categoria] [lugar]\n"
            "Ejemplo: super 450 comida carrefour"
        )
        return

    tokens = text.split()

    if len(tokens) < 2:
        await update.message.reply_text(
            "Formato inválido.\nUsa: descripcion monto [categoria] [lugar]\n"
            "Ejemplo: super 450 comida carrefour"
        )
        return

    # -------------------------------------------------------------------
    #   PARSEO FLEXIBLE:
    #   2 tokens  -> descripcion + monto
    #   3 tokens  -> descripcion + monto + categoria
    #   >=4 tokens -> descripcion + monto + categoria + lugar
    # -------------------------------------------------------------------

    if len(tokens) == 2:
        description = tokens[0]
        amount_token = tokens[1]
        category = "General"
        lugar = "N/A"

    elif len(tokens) == 3:
        description = tokens[0]
        amount_token = tokens[1]
        category = tokens[2]
        lugar = "N/A"

    else:
        # Caso: DESCRIPCIÓN con espacios
        # tokens[-1] = lugar
        # tokens[-2] = categoría
        # tokens[-3] = monto
        # el resto = descripción
        lugar = tokens[-1]
        category = tokens[-2]
        amount_token = tokens[-3]
        description = " ".join(tokens[:-3])

    # -------------------------------------------------------------------
    #                     VALIDAR MONTO
    # -------------------------------------------------------------------
    if not AMOUNT_REGEX.match(amount_token):
        await update.message.reply_text(
            "Monto inválido. Usa solo números o decimal con punto.\n"
            "Ejemplo: super 450 comida carrefour"
        )
        return

    try:
        amount_value = float(amount_token)
        amount_str = f"{amount_value:.2f}"
    except:
        await update.message.reply_text("No se pudo procesar el monto.")
        return

    fecha = date.today().isoformat()

    row = [fecha, description, amount_str, category, lugar]

    # -------------------------------------------------------------------
    #                     GUARDAR EN GOOGLE SHEETS
    # -------------------------------------------------------------------
    gc = context.application.bot_data.get("gspread_client")
    sheet = context.application.bot_data.get("sheet_instance")

    if gc is None or sheet is None:
        await update.message.reply_text("Error interno del servidor.")
        logger.error("gspread_client o sheet_instance no inicializados.")
        return

    loop = asyncio.get_running_loop()
    try:
        # Ejecutamos append_row en executor ya que es bloqueante
        await loop.run_in_executor(
            None,
            lambda: sheet.append_row(row, value_input_option="USER_ENTERED")
        )
    except Exception as e:
        logger.exception("Error al guardar en Sheets: %s", e)
        await update.message.reply_text(
            "Error al guardar en Google Sheets. Revisa logs."
        )
        return

    # Confirmación al usuario
    await update.message.reply_text(
        f"Guardado 🟢\n"
        f"Fecha: {fecha}\n"
        f"Descripción: {description}\n"
        f"Monto: {amount_str}\n"
        f"Categoría: {category}\n"
        f"Lugar: {lugar}"
    )


# -------------------------------------------------------------------
#                  INICIALIZACIÓN DEL BOT (Fly.io)
# -------------------------------------------------------------------

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Inicializar Google Sheets desde secrets
    try:
        gc = init_gspread_from_env()
        # Nombre exacto de tu sheet
        SHEET_NAME = "CuentasBOT"
        sh = gc.open(SHEET_NAME)
        sheet = sh.sheet1  # primera hoja
    except Exception as e:
        logger.exception("Error inicializando Google Sheets: %s", e)
        raise SystemExit("No se pudo inicializar Google Sheets.")

    app.bot_data["gspread_client"] = gc
    app.bot_data["sheet_instance"] = sheet

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Inicialización manual recomendada
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    logger.info("Bot iniciado en Fly.io. Esperando mensajes...")

    # Mantener proceso corriendo
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
