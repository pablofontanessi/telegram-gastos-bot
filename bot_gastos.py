# bot_gastos.py
# Requisitos: python-telegram-bot v20+, gspread, google-auth
# Modifica únicamente: TOKEN, CREDENTIALS_FILE, SHEET_NAME

import asyncio
import re
from datetime import date
import logging

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound

# --------- CONFIGURACIÓN (editar aquí) ----------
TOKEN = "7666727164:AAFjxLzuqqmPn7YRGD_VpZ_35JlIXRQLrA8"         # <-- pega tu token de BotFather aquí
CREDENTIALS_FILE = "google_credentials.json" # <-- nombre del JSON que descargaste
SHEET_NAME = "CuentasBOT"               # <-- nombre del Google Sheet (tal como aparece en Drive)
# -------------------------------------------------

# Logging básico
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Regex para validar monto: enteros o decimales con punto (ej: 450, 12.50)
AMOUNT_REGEX = re.compile(r"^\d+(\.\d+)?$")

# Inicializar cliente gspread una vez (se intentará al iniciar el bot)
def init_gspread_client(credentials_file: str):
    try:
        gc = gspread.service_account(filename=credentials_file)
        return gc
    except Exception as e:
        logger.exception("Error al inicializar gspread con '%s': %s", credentials_file, e)
        raise

# Función que hace append en la hoja (bloqueante) — la ejecutamos en executor para no bloquear el loop async.
def append_row_to_sheet(sheet, row):
    # append_row usa la API y es bloqueante
    sheet.append_row(row, value_input_option="USER_ENTERED")

# Handler asíncrono para mensajes de texto
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    if not text:
        await update.message.reply_text(
            "Mensaje vacío. Envía: descripcion monto [categoria]\nEjemplo: super 450 comida"
        )
        return

    # Separar tokens por espacios. Lógica:
    # - Si hay 2 tokens: descripcion (puede ser una sola palabra) y monto -> categoria = "General"
    # - Si hay >=3 tokens: categoría = ultimo token, monto = penúltimo token, descripcion = resto (puede tener espacios)
    tokens = text.split()
    if len(tokens) < 2:
        await update.message.reply_text(
            "Error: formato inválido. Debes enviar al menos descripción y monto.\nEjemplo válido: super 450 comida"
        )
        return

    if len(tokens) == 2:
        description = tokens[0]
        amount_token = tokens[1]
        category = "General"
    else:
        # >=3 tokens
        category = tokens[-1]
        amount_token = tokens[-2]
        description = " ".join(tokens[:-2])

    # Validar monto (enteros o decimales con punto)
    if not AMOUNT_REGEX.match(amount_token):
        await update.message.reply_text(
            "Monto inválido. Usa sólo dígitos o decimal con punto (ej: 450 o 12.50).\nEjemplo: super 450 comida"
        )
        return

    # Convertir monto a formato estándar (dos decimales), pero guardamos como texto tal cual o como float formateado
    try:
        amount_value = float(amount_token)
        # opcional: formatear a 2 decimales
        amount_str = f"{amount_value:.2f}"
    except Exception:
        await update.message.reply_text(
            "No se pudo procesar el monto. Asegúrate de enviar números (ej: 450 o 12.50)."
        )
        return

    fecha = date.today().isoformat()  # YYYY-MM-DD

    # Preparar fila
    row = [fecha, description, amount_str, category]

    # Intentar obtener el cliente gspread y la hoja desde el objeto en context (inicializado en main)
    gc = context.application.bot_data.get("gspread_client")
    sheet = context.application.bot_data.get("sheet_instance")

    if gc is None or sheet is None:
        await update.message.reply_text(
            "Error del servidor: no se pudo conectar a Google Sheets. Contacta al administrador."
        )
        logger.error("gspread_client o sheet_instance no inicializados.")
        return

    # Ejecutar append en executor para no bloquear
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, append_row_to_sheet, sheet, row)
    except SpreadsheetNotFound:
        await update.message.reply_text(
            f"Error: la planilla '{SHEET_NAME}' no se encontró. Revisa el nombre del Sheet en la configuración."
        )
        logger.exception("SpreadsheetNotFound: %s", SHEET_NAME)
        return
    except APIError as e:
        await update.message.reply_text(
            "Error al acceder a Google Sheets (API). Revisa credenciales y permisos."
        )
        logger.exception("APIError al hacer append: %s", e)
        return
    except Exception as e:
        await update.message.reply_text(
            "Error inesperado al guardar. Revisa los logs del bot."
        )
        logger.exception("Error al hacer append a la hoja: %s", e)
        return

    # Confirmación al usuario
    await update.message.reply_text(
        f"Guardado ✅\nFecha: {fecha}\nDescripción: {description}\nMonto: {amount_str}\nCategoría: {category}"
    )


async def main():
    # Inicializar aplicación telegram
    app = ApplicationBuilder().token(TOKEN).build()

    # Inicializar gspread y abrir sheet (primer hoja)
    try:
        gc = init_gspread_client(CREDENTIALS_FILE)
        sh = gc.open(SHEET_NAME)
        sheet = sh.sheet1  # primera hoja
    except Exception as e:
        logger.exception("Error inicializando Google Sheets: %s", e)
        raise

    # Guardar cliente y sheet
    app.bot_data["gspread_client"] = gc
    app.bot_data["sheet_instance"] = sheet

    # Añadir handler
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # IMPORTANTE: inicializar manualmente por pasos
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    print("Bot iniciado. Esperando mensajes...")

    # Esperar indefinidamente
    await asyncio.Event().wait()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


