# src/main.py
import asyncio
import traceback
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .config import settings
from . import handlers

# Configurar logs para ver errores en la consola del servidor
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

flask_app = Flask(__name__)

# --- INICIALIZACIÓN GLOBAL ---
# Creamos la app AQUÍ, una sola vez al arrancar el servidor.
bot_app = Application.builder().token(settings.TELEGRAM_TOKEN).build()

# Registramos handlers UNA sola vez
bot_app.add_handler(CommandHandler("start", handlers.start))
bot_app.add_handler(CommandHandler("agregar_temas", handlers.agregar_temas))
bot_app.add_handler(CommandHandler("estudiar_temas", handlers.estudiar_temas)) # Nuevo
bot_app.add_handler(CommandHandler("estudiar", handlers.estudiar))
bot_app.add_handler(CommandHandler("dominado", handlers.dominado)) # Nuevo
bot_app.add_handler(CommandHandler("repasar", handlers.repasar))
bot_app.add_handler(CommandHandler("temasFaltantes", handlers.metricas_globales)) # Nuevo
bot_app.add_handler(CommandHandler("materias_metricas", handlers.metricas_materia)) # Nuevo
# Fallback para mensajes desconocidos
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.unknown))

# Inicializamos la app asíncronamente al arrancar (truco para Flask)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(bot_app.initialize())

@flask_app.route('/webhook', methods=['POST'])
async def webhook():
    """
    Endpoint optimizado.
    """
    if request.method == 'POST':
        try:
            update_data = request.get_json(force=True)
            if not update_data: return 'No data', 400
            
            update = Update.de_json(update_data, bot_app.bot)
            
            # Procesamos el update directamente.
            # Al ser función async y Flask soportar async en versiones recientes, 
            # esto es mucho más rápido.
            await bot_app.process_update(update)
                
            return 'OK', 200
        except Exception:
            traceback.print_exc()
            return 'Error interno', 500

@flask_app.route('/health', methods=['GET'])
def health_check():
    return 'Bot activo y rápido 🚀', 200

# Si usas waitress para prod:
def run_prod():
    from waitress import serve
    serve(flask_app, host='0.0.0.0', port=settings.PORT)

if __name__ == '__main__':
    # Para desarrollo local
    flask_app.run(host='0.0.0.0', port=settings.PORT)