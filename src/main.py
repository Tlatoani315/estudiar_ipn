# src/main.py
import asyncio
import traceback
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from waitress import serve

from .config import settings
from . import handlers

# Configuración de logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)

# --- INICIALIZACIÓN GLOBAL ---
# Creamos la app UNA sola vez.
bot_app = Application.builder().token(settings.TELEGRAM_TOKEN).build()

# Registramos los comandos una sola vez aquí

bot_app.add_handler(CommandHandler("start", handlers.start))
bot_app.add_handler(CommandHandler("agregar_temas", handlers.agregar_temas))
bot_app.add_handler(CommandHandler("estudiar_temas", handlers.estudiar_temas))
bot_app.add_handler(CommandHandler("estudiar", handlers.estudiar))
bot_app.add_handler(CommandHandler("dominado", handlers.dominado))
bot_app.add_handler(CommandHandler("repasar", handlers.repasar))
bot_app.add_handler(CommandHandler("temasFaltantes", handlers.metricas_globales))
bot_app.add_handler(CommandHandler("materias_metricas", handlers.metricas_materia))
bot_app.add_handler(CommandHandler("eliminar", handlers.eliminar))
bot_app.add_handler(CommandHandler("materias", handlers.listar_materias))
bot_app.add_handler(CommandHandler("temario", handlers.listar_temario))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.unknown))

async def run_bot_update(update):
    """Función auxiliar asíncrona que gestiona el update."""
    if not bot_app._initialized:
        await bot_app.initialize()
    await bot_app.process_update(update)

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """
    Ruta SÍNCRONA (def, no async def).
    Esto es crucial para que funcione bien con Waitress sin errores de 'async extra'.
    """
    if request.method == 'POST':
        try:
            update_data = request.get_json(force=True)
            if not update_data: 
                return 'No data', 400
            
            # Convertir JSON a objeto Update
            update = Update.de_json(update_data, bot_app.bot)
            
            # Ejecutamos el bot asíncrono dentro de este contexto síncrono
            asyncio.run(run_bot_update(update))
                
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error procesando update: {e}")
            traceback.print_exc()
            # Devolvemos 200 para que Telegram deje de reintentar si hay un error de código
            return 'Error interno procesado', 200

@flask_app.route('/health', methods=['GET'])
def health_check():
    return 'Bot activo 🚀', 200

def main():
    print(f"Iniciando servidor en puerto {settings.PORT}...")
    serve(flask_app, host='0.0.0.0', port=settings.PORT)

if __name__ == '__main__':
    main()