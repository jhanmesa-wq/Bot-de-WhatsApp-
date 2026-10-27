import os
import re
import json
import base64
import sqlite3
import threading
import requests
from flask import Flask
from waitress import serve
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                          ContextTypes)

# ──────────────────────────────────────────────
# CONFIGURACIÓN (variables de entorno)
# ──────────────────────────────────────────────
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PUERTO = int(os.getenv("PORT", "10000"))
CODART_TOKEN = os.getenv("CODART_TOKEN", "").strip()
API_BASE = os.getenv("API_BASE", "https://api-codart.cgrt.org/api/v1/consultas/fd").rstrip("/")
DB_PATH = os.getenv("DB_PATH", "creditos.sqlite3")
CREDITOS_INICIALES = 2
COSTOS = {"dni": 5}

app = Flask(__name__)

@app.route('/')
def mantener_vivo():
    return "✅ Bot activo y funcionando 24/7"

def iniciar_servidor_web():
    serve(app, host="0.0.0.0", port=PUERTO)

# ──────────────────────────────────────────────
# BASE DE DATOS GLOBAL DE CRÉDITOS
# ──────────────────────────────────────────────
def conectar_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    with conectar_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            creditos INTEGER NOT NULL,
            celular TEXT
        )""")
        columnas = {row[1] for row in conn.execute("PRAGMA table_info(usuarios)")}
        if "celular" not in columnas:
            conn.execute("ALTER TABLE usuarios ADD COLUMN celular TEXT")

def asegurar_usuario(user_id):
    with conectar_db() as conn:
        conn.execute("INSERT OR IGNORE INTO usuarios (user_id, creditos, celular) VALUES (?, ?, NULL)",
                     (int(user_id), CREDITOS_INICIALES))

def get_creditos(user_id):
    asegurar_usuario(user_id)
    with conectar_db() as conn:
        row = conn.execute("SELECT creditos FROM usuarios WHERE user_id = ?", (int(user_id),)).fetchone()
        return int(row[0]) if row else 0

def descontar_creditos(user_id, cantidad):
    asegurar_usuario(user_id)
    with conectar_db() as conn:
        cur = conn.execute("UPDATE usuarios SET creditos = creditos - ? WHERE user_id = ? AND creditos >= ?",
                           (int(cantidad), int(user_id), int(cantidad)))
        return cur.rowcount == 1

def reembolsar(user_id, cantidad):
    asegurar_usuario(user_id)
    with conectar_db() as conn:
        conn.execute("UPDATE usuarios SET creditos = creditos + ? WHERE user_id = ?",
                     (int(cantidad), int(user_id)))

def agregar_creditos(user_id, cantidad):
    asegurar_usuario(user_id)
    with conectar_db() as conn:
        conn.execute("UPDATE usuarios SET creditos = creditos + ? WHERE user_id = ?",
                     (int(cantidad), int(user_id)))

# ──────────────────────────────────────────────
# MENÚ DE WHATSAPP (vinculación autorizada)
# ──────────────────────────────────────────────
def teclado_whatsapp():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Abrir WhatsApp Web", url="https://web.whatsapp.com/")],
        [InlineKeyboardButton("📱 Abrir WhatsApp", url="https://www.whatsapp.com/download/")],
        [InlineKeyboardButton("🔄 Actualizar estado", callback_data="wa_estado")],
        [InlineKeyboardButton("❌ Cerrar menú", callback_data="wa_cerrar")],
    ])

async def cmd_whatsapp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🟢 <b>WHATSAPP · CENTRO DE VINCULACIÓN</b>\n\n"
        "Vincula únicamente una cuenta que controles. Abre WhatsApp Web y completa "
        "el proceso oficial desde tu teléfono: WhatsApp → Dispositivos vinculados → Vincular dispositivo.\n\n"
        "🔐 Por seguridad, este bot no genera ni captura códigos de vinculación de terceros y no crea sesiones ocultas."
    )
    await update.effective_message.reply_text(texto, parse_mode="HTML", reply_markup=teclado_whatsapp())

async def whatsapp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "wa_estado":
        await query.edit_message_text(
            "📊 <b>Estado de WhatsApp</b>\n\nEste bot no mantiene una sesión de WhatsApp conectada. "
            "Abre WhatsApp Web y verifica el estado en Dispositivos vinculados.",
            parse_mode="HTML", reply_markup=teclado_whatsapp())
    elif query.data == "wa_cerrar":
        await query.edit_message_text("Menú de WhatsApp cerrado.")

# ──────────────────────────────────────────────
# COMANDO /DNI — 5 CRD
# ──────────────────────────────────────────────
def codart_consultar_dni(dni):
    if not CODART_TOKEN:
        raise RuntimeError("Falta configurar CODART_TOKEN en las variables de entorno.")
    url = f"{API_BASE}/dni/{dni}"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CODART_TOKEN}"}
    response = requests.get(url, headers=headers, timeout=30)
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(f"La API respondió con contenido no válido (HTTP {response.status_code}).")
    if response.status_code >= 400 or not payload.get("success"):
        raise RuntimeError(payload.get("message") or f"La consulta falló (HTTP {response.status_code}).")
    return payload

def texto_dni(payload):
    data = payload.get("data") or {}
    dni = data.get("dni") or {}
    nacimiento = data.get("nacimiento") or {}
    general = data.get("informacion_general") or {}
    domicilio = data.get("domicilio") or {}
    ubigeos = data.get("ubigeos") or {}
    def val(obj, key, default="No disponible"):
        value = obj.get(key, default) if isinstance(obj, dict) else default
        return str(value) if value not in (None, "") else default
    lineas = [
        "🪪 <b>CONSULTA DNI</b>",
        f"<b>DNI:</b> {val(dni, 'completo', val(dni, 'numero'))}",
        f"<b>Nombres:</b> {val(data, 'nombres')}",
        f"<b>Apellidos:</b> {val(data, 'apellidos')}",
        f"<b>Género:</b> {val(data, 'genero')}",
        "", "🎂 <b>NACIMIENTO</b>",
        f"<b>Fecha:</b> {val(nacimiento, 'fecha')}",
        f"<b>Edad:</b> {val(nacimiento, 'edad')}",
        f"<b>Ubicación:</b> {val(nacimiento, 'departamento')}, {val(nacimiento, 'provincia')}, {val(nacimiento, 'distrito')}",
        "", "📄 <b>INFORMACIÓN GENERAL</b>",
        f"<b>Educación:</b> {val(general, 'nivel_educativo')}",
        f"<b>Estado civil:</b> {val(general, 'estado_civil')}",
        f"<b>Estatura:</b> {val(general, 'estatura')}",
        f"<b>Emisión:</b> {val(general, 'fecha_emision')}",
        f"<b>Caducidad:</b> {val(general, 'fecha_caducidad')}",
        f"<b>Donante:</b> {val(general, 'donante_organos')}",
        f"<b>Restricción:</b> {val(general, 'restriccion')}",
        "", "📍 <b>DOMICILIO</b>",
        f"<b>Dirección:</b> {val(domicilio, 'direccion')}",
        f"<b>Distrito:</b> {val(domicilio, 'distrito')}",
        f"<b>Provincia:</b> {val(domicilio, 'provincia')}",
        f"<b>Departamento:</b> {val(domicilio, 'departamento')}",
        "", "🔎 <b>UBIGEOS</b>",
        f"<b>RENIEC:</b> {val(ubigeos, 'reniec')}",
        f"<b>INE:</b> {val(ubigeos, 'ine')}",
        f"<b>SUNAT:</b> {val(ubigeos, 'sunat')}",
    ]
    return "\n".join(lineas), data.get("images") or []

async def cmd_dni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user_id = update.effective_user.id
    if not context.args:
        await message.reply_text("Uso: /dni 12345678\nCosto: 5 CRD")
        return
    dni = context.args[0].strip()
    if not re.fullmatch(r"\d{8}", dni):
        await message.reply_text("❌ El DNI debe contener exactamente 8 dígitos.\nUso: /dni 12345678")
        return
    saldo = get_creditos(user_id)
    costo = COSTOS["dni"]
    if saldo < costo:
        await message.reply_text(f"❌ Créditos insuficientes.\n💳 Saldo: {saldo} CRD\n💰 Requerido: {costo} CRD")
        return
    if not descontar_creditos(user_id, costo):
        await message.reply_text("❌ No se pudo reservar el costo de la consulta. Inténtalo nuevamente.")
        return
    estado = await message.reply_text("🔎 Consultando DNI…\n⏳ Espera un momento.")
    try:
        payload = await __import__("asyncio").to_thread(codart_consultar_dni, dni)
        texto, imagenes = texto_dni(payload)
        await estado.edit_text(texto, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Consultar otro DNI", callback_data="dni_otro")],
            [InlineKeyboardButton("💳 Ver saldo", callback_data="ver_saldo")],
        ]))
        # Enviar las imágenes data_uri de la API, si existen.
        for item in imagenes:
            uri = item.get("data_uri", "") if isinstance(item, dict) else ""
            match = re.fullmatch(r"data:image/([a-zA-Z0-9.+-]+);base64,(.+)", uri, re.DOTALL)
            if match:
                try:
                    raw = base64.b64decode(match.group(2), validate=True)
                    await message.reply_photo(photo=raw, caption="🖼️ Imagen devuelta por la consulta")
                except Exception:
                    pass
        await message.reply_text(f"✅ Consulta completada. Se descontaron {costo} CRD. Saldo: {get_creditos(user_id)} CRD.")
    except Exception as exc:
        reembolsar(user_id, costo)
        await estado.edit_text(f"⚠️ No se pudo completar la consulta. Se reembolsaron {costo} CRD.\nDetalle: {str(exc)[:300]}")

async def botones_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "ver_saldo":
        await query.message.reply_text(f"💳 Tu saldo actual es: {get_creditos(query.from_user.id)} CRD")
    elif query.data == "dni_otro":
        await query.message.reply_text("Envía el DNI así: /dni 12345678")

async def cmd_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(f"💳 Saldo actual: {get_creditos(update.effective_user.id)} CRD")

async def cmd_sumar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or ADMIN_ID == 0:
        await update.effective_message.reply_text("🔒 Sin permiso")
        return
    if len(context.args) != 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        await update.effective_message.reply_text("Uso: /sumar ID_USUARIO CANTIDAD")
        return
    uid, cantidad = int(context.args[0]), int(context.args[1])
    if cantidad <= 0:
        await update.effective_message.reply_text("La cantidad debe ser mayor que cero.")
        return
    agregar_creditos(uid, cantidad)
    await update.effective_message.reply_text(f"✅ Añadidos {cantidad} CRD al usuario {uid}. Saldo: {get_creditos(uid)} CRD")

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or ADMIN_ID == 0:
        return
    await update.effective_message.reply_text("📊 Estado: bot activo. No hay sesiones de navegador de WhatsApp administradas por este bot.")

# ──────────────────────────────────────────────
# ARRANQUE
# ──────────────────────────────────────────────
def iniciar_bot():
    if not TOKEN_TELEGRAM:
        raise RuntimeError("Falta configurar TOKEN_TELEGRAM en las variables de entorno.")
    init_db()
    threading.Thread(target=iniciar_servidor_web, daemon=True).start()
    application = ApplicationBuilder().token(TOKEN_TELEGRAM).build()
    application.add_handler(CommandHandler("dni", cmd_dni))
    application.add_handler(CommandHandler("whatsapp", cmd_whatsapp))
    application.add_handler(CommandHandler("wa", cmd_whatsapp))
    application.add_handler(CommandHandler("saldo", cmd_saldo))
    application.add_handler(CommandHandler("sumar", cmd_sumar))
    application.add_handler(CommandHandler("estado", cmd_estado))
    application.add_handler(CallbackQueryHandler(whatsapp_callback, pattern=r"^wa_(estado|cerrar)$"))
    application.add_handler(CallbackQueryHandler(botones_callback, pattern=r"^(dni_otro|ver_saldo)$"))
    print("🤖 Bot iniciado; comandos /dni, /whatsapp, /saldo, /estado")
    application.run_polling()

if __name__ == "__main__":
    iniciar_bot()
