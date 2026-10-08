import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from time import sleep
import random
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pyvirtualdisplay import Display
from flask import Flask
import threading
import os

# ──────────────────────────────────────────────
# CONFIGURACIÓN (LEE DESDE VARIABLES DE RENDER)
# ──────────────────────────────────────────────
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PUERTO = int(os.getenv("PORT", 10000))

SESIONES_ACTIVAS = []

# Servidor web para mantener vivo el bot
app = Flask(__name__)

@app.route('/')
def mantener_vivo():
    return "✅ Bot activo y funcionando 24/7"

def iniciar_servidor_web():
    from waitress import serve
    serve(app, host="0.0.0.0", port=PUERTO)

# ──────────────────────────────────────────────
# FUNCIONES AUXILIARES
# ──────────────────────────────────────────────
def retardo_humano(min_seg=0.8, max_seg=2.5):
    sleep(random.uniform(min_seg, max_seg))

# ──────────────────────────────────────────────
# CLASE SESIÓN WHATSAPP
# ──────────────────────────────────────────────
class SesionWhatsApp:
    def __init__(self, nombre_sesion, perfil_ruta, numero_whatsapp=None):
        self.nombre = nombre_sesion
        self.perfil = perfil_ruta
        self.numero = numero_whatsapp
        self.driver = None
        self.wait = None
        self.bloqueado = False
        self.codigo_vinculacion = None

    def iniciar_navegador(self):
        if self.bloqueado:
            return False
        opciones = uc.ChromeOptions()
        opciones.add_argument("--start-maximized")
        opciones.add_argument("--no-sandbox")
        opciones.add_argument("--disable-dev-shm-usage")
        opciones.add_argument("--disable-gpu")
        opciones.add_argument(f"--user-data-dir={self.perfil}")
        opciones.add_argument("--disable-blink-features=AutomationControlled")
        opciones.add_argument("--disable-extensions")
        opciones.add_argument("--disable-default-apps")
        # Modo sin pantalla para Render
        opciones.add_argument("--headless=new")
        opciones.add_argument("--window-size=1920,1080")

        self.driver = uc.Chrome(
            options=opciones,
            version_main=None,
            suppress_welcome=True
        )
        self.wait = WebDriverWait(self.driver, 25)
        return True

    def cargar_y_obtener_codigo(self):
        if not self.driver:
            return False
        try:
            self.driver.get('https://web.whatsapp.com/')
            retardo_humano(3, 5)

            try:
                usar_codigo_btn = self.wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//span[contains(text(), "vincular con número") or contains(text(), "Link with phone number")] | //button[@data-testid="link-device-qr-switch"]')
                    )
                )
                usar_codigo_btn.click()
                retardo_humano(2, 3)
            except:
                print(f"ℹ️ [{self.nombre}] Ya en vista de código o sesión iniciada")

            if self.numero:
                try:
                    numero_input = self.wait.until(
                        EC.element_to_be_clickable(
                            (By.XPATH, '//input[@data-testid="link-device-phone-number-input"] | //input[@type="tel"]')
                        )
                    )
                    numero_input.click()
                    retardo_humano()
                    numero_input.clear()
                    for digito in self.numero:
                        numero_input.send_keys(digito)
                        sleep(random.uniform(0.08, 0.15))
                    retardo_humano(1, 2)

                    continuar_btn = self.wait.until(
                        EC.element_to_be_clickable(
                            (By.XPATH, '//button//span[contains(text(), "Continuar") or contains(text(), "Next")] | //div[@data-testid="link-device-phone-number-next"]')
                        )
                    )
                    continuar_btn.click()
                    retardo_humano(2, 4)
                except Exception as e:
                    print(f"ℹ️ [{self.nombre}] Número ya ingresado: {str(e)[:40]}...")

            try:
                codigos_elementos = self.wait.until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH, '//div[@data-testid="link-device-code"]//span | //div[contains(@class, "link-device-code")]//span')
                    )
                )
                if codigos_elementos:
                    self.codigo_vinculacion = ''.join([el.text.strip() for el in codigos_elementos])
                    print(f"🔑 [{self.nombre}] CÓDIGO: {self.codigo_vinculacion}")
                    return True
            except:
                pass

            try:
                self.wait.until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//div[@data-testid="chat-list-search"]')
                    )
                )
                print(f"✅ [{self.nombre}] SESIÓN CONECTADA")
                self.codigo_vinculacion = "CONECTADO"
                return True
            except:
                pass

            return False
        except Exception as e:
            print(f"❌ [{self.nombre}] Error carga: {str(e)}")
            return False

    def reportar_numero(self, numero_objetivo):
        if not self.driver or self.bloqueado:
            return f"❌ [{self.nombre}] No disponible"
        try:
            search_box = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//div[@contenteditable="true" and @data-testid="chat-list-search"]')
                )
            )
            search_box.click()
            retardo_humano()
            search_box.clear()
            for digito in numero_objetivo:
                search_box.send_keys(digito)
                sleep(random.uniform(0.08, 0.15))
            retardo_humano(1.5, 3)

            primer_chat = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '(//div[@data-testid="cell-frame-container"])[1]')
                )
            )
            primer_chat.click()
            retardo_humano(2, 3)

            boton_mas = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, '//span[@data-testid="menu"]'))
            )
            boton_mas.click()
            retardo_humano(1, 2)

            opcion_reportar = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//li[contains(., "Reportar") or @data-testid="contact-report"]')
                )
            )
            opcion_reportar.click()
            retardo_humano(1, 2)

            opcion_spam = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//*[contains(text(), "spam")] | //span[@data-testid="report-reason-option-spam"]')
                )
            )
            opcion_spam.click()
            retardo_humano(0.8, 1.5)

            boton_confirmar = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//button//span[contains(text(), "Reportar")] | //div[@data-testid="submit-button"]')
                )
            )
            ActionChains(self.driver).move_to_element(boton_confirmar).pause(0.3).click().perform()

            retardo_humano(1, 2)
            return f"✅ [{self.nombre}] Reportó a {numero_objetivo}"
        except Exception as e:
            return f"⚠️ [{self.nombre}] Falló: {str(e)[:60]}"

    def cerrar(self):
        if self.driver:
            self.driver.quit()
            print(f"🔌 [{self.nombre}] Cerrado")

# ──────────────────────────────────────────────
# EJECUCIÓN PARALELA
# ──────────────────────────────────────────────
def ejecutar_reporte_en_una_sesion(sesion, numero):
    return sesion.reportar_numero(numero)

async def reportar_en_todas(numero: str):
    resultados = []
    with ThreadPoolExecutor(max_workers=len(SESIONES_ACTIVAS)) as executor:
        tareas = [
            asyncio.get_event_loop().run_in_executor(
                executor, ejecutar_reporte_en_una_sesion, sesion, numero
            )
            for sesion in SESIONES_ACTIVAS
        ]
        resultados = await asyncio.gather(*tareas)
    return resultados

# ──────────────────────────────────────────────
# COMANDOS TELEGRAM
# ──────────────────────────────────────────────
async def cmd_reportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🔒 Sin permiso")
        return
    if not context.args:
        await update.message.reply_text("Uso: /reportar NUMERO\nEj: /reportar 987654321")
        return
    numero_objetivo = context.args[0]
    await update.message.reply_text(
        f"🚀 Reportando en {len(SESIONES_ACTIVAS)} cuentas...\n🎯: {numero_objetivo}"
    )
    resultados = await reportar_en_todas(numero_objetivo)
    await update.message.reply_text("📋 RESULTADOS:\n" + "\n".join(resultados))

async def cmd_codigos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = "📋 CÓDIGOS DE VINCULACIÓN:\n\n"
    for s in SESIONES_ACTIVAS:
        if s.codigo_vinculacion == "CONECTADO":
            msg += f"✅ {s.nombre}: CONECTADO\n"
        elif s.codigo_vinculacion:
            msg += f"🔑 {s.nombre}: {s.codigo_vinculacion}\n"
        else:
            msg += f"⏳ {s.nombre}: Cargando...\n"
    await update.message.reply_text(msg)

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    activas = sum(1 for s in SESIONES_ACTIVAS if s.codigo_vinculacion == "CONECTADO")
    await update.message.reply_text(
        f"📊 ESTADO:\nTotal: {len(SESIONES_ACTIVAS)}\nConectadas: {activas}"
    )

# ──────────────────────────────────────────────
# INICIALIZACIÓN
# ──────────────────────────────────────────────
def configurar_sesiones():
    # === TUS CUENTAS AQUÍ ===
    datos_sesiones = [
        {"nombre": "Cuenta_1", "perfil": "./wa_perfil_1", "numero": "+51987654321"},
        {"nombre": "Cuenta_2", "perfil": "./wa_perfil_2", "numero": "+51999888777"},
        # Agrega más aquí
    ]
    for d in datos_sesiones:
        sesion = SesionWhatsApp(d["nombre"], d["perfil"], d["numero"])
        SESIONES_ACTIVAS.append(sesion)
    print(f"🔧 {len(SESIONES_ACTIVAS)} sesiones configuradas")

def iniciar_bot():
    configurar_sesiones()
    # Iniciar pantalla virtual para Render
    display = Display(visible=0, size=(1920, 1080))
    display.start()
    print("🖥️ Pantalla virtual iniciada")

    # Iniciar navegadores
    for sesion in SESIONES_ACTIVAS:
        sesion.iniciar_navegador()
        sesion.cargar_y_obtener_codigo()
        retardo_humano(1, 2)

    # Iniciar servidor web en hilo separado → mantiene vivo
    threading.Thread(target=iniciar_servidor_web, daemon=True).start()
    print("🌐 Servidor anti-sueño activo")

    # Iniciar bot de Telegram
    application = ApplicationBuilder().token(TOKEN_TELEGRAM).build()
    application.add_handler(CommandHandler("reportar", cmd_reportar))
    application.add_handler(CommandHandler("codigos", cmd_codigos))
    application.add_handler(CommandHandler("estado", cmd_estado))
    print("🤖 BOT INICIADO — Comandos: /codigos /reportar /estado")
    application.run_polling()

if __name__ == "__main__":
    iniciar_bot()
    for s in SESIONES_ACTIVAS:
        s.cerrar()
  
