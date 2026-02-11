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

def build_application():
    """Construye una instancia nueva de la App para cada petición."""
    app = Application.builder().token(settings.TELEGRAM_TOKEN).build()

    # Registro de Handlers
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("agregar_temas", handlers.agregar_temas))
    app.add_handler(CommandHandler("estudiar_temas", handlers.estudiar_temas))
    app.add_handler(CommandHandler("estudiar", handlers.estudiar))
    app.add_handler(CommandHandler("dominado", handlers.dominado))
    app.add_handler(CommandHandler("repasar", handlers.repasar))
    app.add_handler(CommandHandler("temasFaltantes", handlers.metricas_globales))
    app.add_handler(CommandHandler("materias_metricas", handlers.metricas_materia))
    app.add_handler(CommandHandler("eliminar", handlers.eliminar))
    app.add_handler(CommandHandler("materias", handlers.listar_materias))
    app.add_handler(CommandHandler("temario", handlers.listar_temario))
    app.add_handler(CommandHandler("ver_calendario", handlers.ver_calendario))
    # Handler por defecto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.unknown))
    
    return app

async def process_update_async(update_data):
    """Procesa el update en un contexto asíncrono aislado."""
    bot_app = build_application()
    
    # 'async with' gestiona el inicio y cierre correcto de la conexión
    async with bot_app:
        update = Update.de_json(update_data, bot_app.bot)
        await bot_app.process_update(update)

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        try:
            update_data = request.get_json(force=True)
            if not update_data: return 'No data', 400
            
            # Ejecución segura del bot
            asyncio.run(process_update_async(update_data))
                
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error crítico en webhook: {e}")
            traceback.print_exc()
            return 'Error procesado', 200

@flask_app.route('/health', methods=['GET'])
def health_check():
    return 'Bot activo 🚀', 200

def main():
    print(f"Iniciando servidor en puerto {settings.PORT}...")
    serve(flask_app, host='0.0.0.0', port=settings.PORT)

if __name__ == '__main__':
    main()