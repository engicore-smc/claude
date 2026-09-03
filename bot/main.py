"""Bot de Telegram: recibe los tres reportes y devuelve el anexo en Word."""
from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import auth, flow
from .config import settings

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("bot")

BIENVENIDA = (
    "<b>Anexos de tensado</b>\n"
    "Genero las tablas de tensado en Word a partir de los reportes de PLS-CADD.\n\n"
    "Envíame los tres XLSX, en cualquier orden — los reconozco por sus columnas:\n"
    "• Reporte tensado\n"
    "• Reporte flecha y tensión\n"
    "• Reporte Staking table\n\n"
    "Después elijo contigo el conductor y te devuelvo el anexo.\n\n"
    "/nuevo empieza de cero · /estado muestra qué falta · /conductor vuelve a elegir cable"
)


# --------------------------------------------------------------------------
# Envio de respuestas
# --------------------------------------------------------------------------
async def _send(message, reply: flow.Reply) -> None:
    markup = None
    if reply.buttons:
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(label, callback_data=data)] for label, data in reply.buttons]
        )
    if reply.text:
        await message.reply_text(reply.text, parse_mode=ParseMode.HTML, reply_markup=markup)
    if reply.document:
        name, blob = reply.document
        await message.reply_document(document=BytesIO(blob), filename=name)


async def _guard(update: Update) -> bool:
    """Corta el paso a quien no esta autorizado."""
    user = update.effective_user
    if user and auth.is_authorized(user.id):
        return True
    if settings.is_open:
        await update.effective_message.reply_text(
            "El bot no tiene acceso configurado. Define TELEGRAM_ALLOWED_USERS o BOT_PASSWORD."
        )
        return False
    aviso = "No tienes acceso a este bot."
    if settings.password:
        aviso += "\nSi conoces la clave, envía: /clave TU_CLAVE"
    if user:
        aviso += f"\n\nTu ID de Telegram es <code>{user.id}</code>."
    await update.effective_message.reply_text(aviso, parse_mode=ParseMode.HTML)
    return False


# --------------------------------------------------------------------------
# Comandos
# --------------------------------------------------------------------------
async def cmd_clave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    candidata = " ".join(context.args or "").strip()
    try:
        await update.message.delete()  # que la clave no quede en el historial
    except Exception:
        pass
    if user and auth.unlock(user.id, candidata):
        await context.bot.send_message(update.effective_chat.id, BIENVENIDA, parse_mode=ParseMode.HTML)
    else:
        await context.bot.send_message(update.effective_chat.id, "Clave incorrecta.")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    flow.store.reset(update.effective_chat.id)
    await update.message.reply_text(BIENVENIDA, parse_mode=ParseMode.HTML)


async def cmd_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    flow.store.reset(update.effective_chat.id)
    await update.message.reply_text("Empezamos de cero. Envíame los tres reportes XLSX.")


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await _send(update.message, flow.status(flow.store.get(update.effective_chat.id)))


async def cmd_conductor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await _send(update.message, flow.cable_prompt(flow.store.get(update.effective_chat.id)))


async def cmd_salir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        auth.forget(user.id)
    flow.store.reset(update.effective_chat.id)
    await update.message.reply_text("Sesión cerrada.")


# --------------------------------------------------------------------------
# Archivos y botones
# --------------------------------------------------------------------------
async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    documento = update.message.document
    nombre = documento.file_name or "archivo.xlsx"
    if documento.file_size and documento.file_size > settings.max_upload_bytes:
        limite = settings.max_upload_bytes // (1024 * 1024)
        await update.message.reply_text(f"«{nombre}» supera el límite de {limite} MB.")
        return

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    archivo = await documento.get_file()
    contenido = bytes(await archivo.download_as_bytearray())

    sesion = flow.store.get(update.effective_chat.id)
    # Leer y cruzar los XLSX es trabajo de CPU: fuera del hilo del bot.
    reply = await asyncio.to_thread(flow.add_report, sesion, contenido, nombre)
    await _send(update.message, reply)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    consulta = update.callback_query
    await consulta.answer()
    if not await _guard(update):
        return
    if not (consulta.data or "").startswith("cable:"):
        return
    try:
        indice = int(consulta.data.split(":", 1)[1])
    except ValueError:
        return

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_DOCUMENT)
    sesion = flow.store.get(update.effective_chat.id)
    reply = await asyncio.to_thread(flow.generate, sesion, indice)
    await _send(consulta.message, reply)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    sesion = flow.store.get(update.effective_chat.id)
    if sesion.faltan:
        await _send(update.message, flow.status(sesion))
    else:
        await _send(update.message, flow.cable_prompt(sesion))


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Error procesando una actualizacion", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Algo falló procesando eso. Prueba de nuevo o empieza con /nuevo."
        )


COMANDOS = [
    BotCommand("nuevo", "Empezar de cero"),
    BotCommand("estado", "Ver qué reportes faltan"),
    BotCommand("conductor", "Elegir otro conductor"),
    BotCommand("ayuda", "Cómo funciona"),
    BotCommand("salir", "Cerrar sesión"),
]


async def _post_init(application: Application) -> None:
    """Prepara un bot que puede venir usado de antes.

    Si el bot tenia un webhook puesto, getUpdates responde 409 y el long
    polling no arranca nunca; por eso se borra primero. De paso se registra el
    menu de comandos, sin tener que tocar BotFather.
    """
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_my_commands(COMANDOS)
    yo = await application.bot.get_me()
    logger.info("Conectado como @%s (id %s)", yo.username, yo.id)


def build_application() -> Application:
    if not settings.token:
        raise SystemExit("Falta la variable de entorno TELEGRAM_TOKEN.")
    if settings.is_open:
        raise SystemExit(
            "Define TELEGRAM_ALLOWED_USERS (ids separados por comas) o BOT_PASSWORD: "
            "sin ninguna de las dos el bot quedaria abierto a cualquiera."
        )

    application = Application.builder().token(settings.token).post_init(_post_init).build()
    application.add_handler(CommandHandler("clave", cmd_clave))
    application.add_handler(CommandHandler(["start", "ayuda", "help"], cmd_start))
    application.add_handler(CommandHandler("nuevo", cmd_nuevo))
    application.add_handler(CommandHandler("estado", cmd_estado))
    application.add_handler(CommandHandler("conductor", cmd_conductor))
    application.add_handler(CommandHandler("salir", cmd_salir))
    application.add_handler(MessageHandler(filters.Document.ALL, on_document))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_error_handler(on_error)
    return application


def main() -> None:
    application = build_application()
    logger.info("Bot en marcha (long polling)")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
