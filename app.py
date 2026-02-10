import json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from flask import Flask, request, abort

# Tu TOKEN de BotFather
TOKEN = '8257514203:AAHO2mIe0txjFlhHOKb1oA3N-FgeqPG5H6g'

# Archivo para almacenar datos (usaremos JSON simple)
DATA_FILE = 'estudios.json'

# Cargar/guardar datos (mismo que antes)
def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'pendientes': [], 'estudiados': {}, 'repasar': {}}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

# Crea la aplicación Telegram
application = Application.builder().token(TOKEN).build()

# Agrega handlers (mismo que antes)
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text('¡Hola! Soy tu bot de estudios. Usa:\n/addpendiente <tema> - Agregar tema pendiente\n/estudiar <tema> - Marcar como estudiado\n/pendientes - Ver pendientes\n/repasar - Ver qué repasar\n/calendario - Ver temas por fecha')

async def add_pendiente(update: Update, context: CallbackContext):
    tema = ' '.join(context.args)
    if tema:
        data = load_data()
        data['pendientes'].append(tema)
        save_data(data)
        await update.message.reply_text(f'Tema "{tema}" agregado a pendientes.')
    else:
        await update.message.reply_text('Usa /addpendiente <tema>')

async def estudiar(update: Update, context: CallbackContext):
    tema = ' '.join(context.args)
    if tema:
        data = load_data()
        if tema in data['pendientes']:
            data['pendientes'].remove(tema)
        hoy = datetime.now().strftime('%Y-%m-%d')
        data['estudiados'][tema] = hoy
        repaso_fecha = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        if repaso_fecha not in data['repasar']:
            data['repasar'][repaso_fecha] = []
        data['repasar'][repaso_fecha].append(tema)
        save_data(data)
        await update.message.reply_text(f'Tema "{tema}" marcado como estudiado el {hoy}. Repaso programado para {repaso_fecha}.')
    else:
        await update.message.reply_text('Usa /estudiar <tema>')

async def pendientes(update: Update, context: CallbackContext):
    data = load_data()
    if data['pendientes']:
        await update.message.reply_text('Temas pendientes:\n' + '\n'.join(data['pendientes']))
    else:
        await update.message.reply_text('No hay temas pendientes.')

async def repasar(update: Update, context: CallbackContext):
    data = load_data()
    hoy = datetime.now().strftime('%Y-%m-%d')
    temas = []
    for fecha, lista in data['repasar'].items():
        if fecha <= hoy:
            temas.extend(lista)
    if temas:
        await update.message.reply_text('Temas para repasar:\n' + '\n'.join(temas))
    else:
        await update.message.reply_text('Nada para repasar por ahora.')

async def calendario(update: Update, context: CallbackContext):
    data = load_data()
    cal = {}
    for tema, fecha in data['estudiados'].items():
        if fecha not in cal:
            cal[fecha] = []
        cal[fecha].append(tema)
    if cal:
        texto = 'Calendario de temas estudiados:\n'
        for fecha in sorted(cal.keys()):
            texto += f'{fecha}: {", ".join(cal[fecha])}\n'
        await update.message.reply_text(texto)
    else:
        await update.message.reply_text('No hay temas estudiados aún.')

async def echo(update: Update, context: CallbackContext):
    await update.message.reply_text('Usa comandos como /start para ayuda.')

# Registra handlers
application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('addpendiente', add_pendiente))
application.add_handler(CommandHandler('estudiar', estudiar))
application.add_handler(CommandHandler('pendientes', pendientes))
application.add_handler(CommandHandler('repasar', repasar))
application.add_handler(CommandHandler('calendario', calendario))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# Inicializa Flask para webhooks
flask_app = Flask(__name__)

@flask_app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return 'Bot is running!'
    if request.method == 'POST':
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.process_update(update)
        return 'ok', 200
    abort(400)

if __name__ == '__main__':
    from waitress import serve  # Usa waitress para producción (instala pip install waitress)
    serve(flask_app, host='0.0.0.0', port=8080)  # Puerto por defecto en Render