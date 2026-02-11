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

# --- FACTORY DE LA APLICACIÓN ---
def build_application():
    """
    Construye una instancia nueva de la Application para cada petición.
    Es crucial para evitar el error 'Event loop is closed'.
    """
    app = Application.builder().token(settings.TELEGRAM_TOKEN).build()

    # Registramos los comandos AQUÍ para cada nueva instancia
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
    
    # Handler por defecto (si no entiende el comando)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.unknown))
    
    return app

async def process_update_async(update_data):
    """
    Gestiona el ciclo de vida completo del bot para una sola actualización.
    """
    bot_app = build_application()
    
    # 'async with' inicializa y cierra la aplicación correctamente en ESTE loop.
    async with bot_app:
        # Importante: Decodificar el JSON usando el bot de esta instancia específica
        update = Update.de_json(update_data, bot_app.bot)
        await bot_app.process_update(update)

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """
    Punto de entrada síncrono para Flask/Waitress.
    """
    if request.method == 'POST':
        try:
            update_data = request.get_json(force=True)
            if not update_data: 
                return 'No data', 400
            
            # Ejecutamos el bot en un entorno asíncrono aislado y seguro
            asyncio.run(process_update_async(update_data))
                
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error procesando update: {e}")
            traceback.print_exc()
            # Retornamos 200 para evitar que Telegram reintente infinitamente en caso de bug
            return 'Error interno procesado', 200

@flask_app.route('/health', methods=['GET'])
def health_check():
    return 'Bot activo 🚀', 200

def main():
    print(f"Iniciando servidor en puerto {settings.PORT}...")
    serve(flask_app, host='0.0.0.0', port=settings.PORT)

if __name__ == '__main__':
    main()