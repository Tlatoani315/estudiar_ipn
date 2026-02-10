import asyncio
import traceback
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from waitress import serve

from .config import settings
from . import handlers

# Inicialización de Flask y Bot
flask_app = Flask(__name__)
bot_app = Application.builder().token(settings.TELEGRAM_TOKEN).build()

# Registro de Handlers
bot_app.add_handler(CommandHandler("start", handlers.start))
bot_app.add_handler(CommandHandler("agregar_temas", handlers.agregar_temas))
bot_app.add_handler(CommandHandler("estudiar", handlers.estudiar))
bot_app.add_handler(CommandHandler("pendientes", handlers.pendientes))
# ... registrar resto de comandos
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.echo))

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint para recibir actualizaciones de Telegram."""
    if request.method == 'POST':
        try:
            update_data = request.get_json(force=True)
            if not update_data: return 'No data', 400
            
            update = Update.de_json(update_data, bot_app.bot)
            
            async def process_safe():
                # Inicialización perezosa (lazy) de la aplicación de bot
                if not bot_app._initialized:
                    await bot_app.initialize()
                    await bot_app.start()
                await bot_app.process_update(update)
            
            # Ejecución asíncrona segura dentro del contexto de Flask
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(process_safe())
            finally:
                loop.close()
                
            return 'OK', 200
        except Exception:
            traceback.print_exc()
            return 'Error interno', 500

@flask_app.route('/health', methods=['GET'])
def health_check():
    return 'Bot activo 🚀', 200

def main():
    print(f"Iniciando servidor en puerto {settings.PORT}...")
    serve(flask_app, host='0.0.0.0', port=settings.PORT)

if __name__ == '__main__':
    main()