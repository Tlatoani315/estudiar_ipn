import os
import asyncio
import traceback
from datetime import datetime, timedelta
from flask import Flask, request, abort
from supabase import create_client, Client
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Carga variables de entorno
load_dotenv()

TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("Faltan variables de entorno")

# Cliente Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Flask app
flask_app = Flask(__name__)

# Telegram Bot (Global)
application = Application.builder().token(TOKEN).build()

# ------------------ LÓGICA DE ESTUDIO (MEJORADA) ------------------

def get_info_tema(tema: str, tipo: str = "pendiente"):
    response = supabase.table("estudios").select("materia, tema, subtema").eq("tipo", tipo).eq("tema", tema).limit(1).execute()
    if response.data:
        r = response.data[0]
        return r["materia"] or "General", r["tema"], r["subtema"]
    return "General", tema, None

def agregar_repaso_siguiente(repasar_row):
    """Calcula la próxima fecha basada en el número de repasos previos (Spaced Repetition)"""
    count = repasar_row.get("repasos_count", 0)
    if count >= 4:
        return # Ya se graduó del sistema de repasos
    
    # Intervalos: 1er repaso (+1 día), 2do (+3), 3ro (+7), 4to (+30)
    dias = [3, 7, 30][min(count-1, 2)] 
    nueva_fecha = (datetime.strptime(repasar_row["fecha"], '%Y-%m-%d') + timedelta(days=dias)).strftime('%Y-%m-%d')
    
    supabase.table("estudios").insert({
        "tipo": "repasar",
        "materia": repasar_row["materia"],
        "tema": repasar_row["tema"],
        "subtema": repasar_row["subtema"],
        "fecha": nueva_fecha,
        "repasos_count": count + 1
    }).execute()

def marcar_estudiado_logica(tema_input: str):
    """
    Retorna (mensaje_status, objeto_info_tema)
    objeto_info_tema es un dict con {materia, tema} para generar los textos finales.
    """
    hoy = datetime.now().strftime('%Y-%m-%d')
    
    # 1. ¿Es un REPASO existente?
    # Busamos si existe en 'repasar' con fecha <= hoy
    resp_repaso = supabase.table("estudios").select("*").eq("tipo", "repasar").eq("tema", tema_input).lte("fecha", hoy).execute()
    
    if resp_repaso.data:
        row = resp_repaso.data[0]
        # Guardar historial
        supabase.table("estudios").insert({
            "tipo": "estudiado",
            "materia": row["materia"],
            "tema": row["tema"],
            "subtema": row["subtema"],
            "fecha": hoy
        }).execute()
        
        # Borrar el pendiente de repaso
        supabase.table("estudios").delete().eq("id", row["id"]).execute()
        
        # Programar siguiente
        agregar_repaso_siguiente(row)
        
        return "Repaso completado", {"materia": row["materia"], "tema": row["tema"]}

    # 2. Es un TEMA NUEVO (Pendiente)
    else:
        materia, tema_real, subtema = get_info_tema(tema_input, "pendiente")
        
        # Eliminar de pendientes
        supabase.table("estudios").delete().eq("tipo", "pendiente").eq("tema", tema_input).execute()
        
        # Marcar estudiado
        supabase.table("estudios").insert({
            "tipo": "estudiado",
            "materia": materia,
            "tema": tema_real,
            "subtema": subtema,
            "fecha": hoy
        }).execute()
        
        # Primer repaso (+1 día)
        repaso_fecha = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        supabase.table("estudios").insert({
            "tipo": "repasar",
            "materia": materia,
            "tema": tema_real,
            "subtema": subtema,
            "fecha": repaso_fecha,
            "repasos_count": 1
        }).execute()
        
        return "Nuevo tema estudiado", {"materia": materia, "tema": tema_real}

# ------------------ HANDLERS ------------------

async def estudiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = ' '.join(context.args).strip()
    if not texto:
        await update.message.reply_text('Uso: /estudiar tema1, tema2...')
        return
    
    temas_raw = [t.strip() for t in texto.split(',') if t.strip()]
    exitosos = [] # Lista de dicts {materia, tema}
    mensajes = []
    
    for tema in temas_raw:
        try:
            msg, info = marcar_estudiado_logica(tema)
            exitosos.append(info)
            mensajes.append(f'✅ "{tema}": {msg}')
        except Exception as e:
            mensajes.append(f'❌ Error en "{tema}": {str(e)}')
            print(f"Error estudiando {tema}: {e}")
            traceback.print_exc()

    # Enviar reporte simple
    await update.message.reply_text("\n".join(mensajes))
    
    # --- GENERAR LOS TEXTOS MAGICOS SOLICITADOS ---
    if exitosos:
        # 1. Texto para Google Keep
        # Agrupamos materias unicas
        materias_unicas = sorted(list(set([x["materia"] for x in exitosos])))
        temas_lista = ", ".join([x["tema"] for x in exitosos])
        materias_str = ", ".join(materias_unicas)
        
        texto_keep = (
            f"De las lisatas que tengo en keep agrega palomita de terminado en la lista "
            f"[{materias_str}], los temas [{temas_lista}]"
        )
        
        # 2. Texto para Calendario
        eventos_lista = ", ".join([f'{x["materia"]}:{x["tema"]}' for x in exitosos])
        texto_cal = (
            f"Agrega en el calendario estos dos eventos que acaban de pasar hoy, "
            f"es para tener un registro de lo que estudié hoy: [{eventos_lista}]"
        )
        
        # Enviar los textos en bloques de código para copiar fácil
        await update.message.reply_text(f"`{texto_keep}`", parse_mode='Markdown')
        await update.message.reply_text(f"`{texto_cal}`", parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Bot de estudios activo 🤖. Usa /estudiar para avanzar.')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Ignorar mensajes sin comando

# Registrar handlers
application.add_handler(CommandHandler("estudiar", estudiar))
application.add_handler(CommandHandler("start", start))
# ... Agrega aquí tus otros handlers (pendientes, calendario, etc) si los tienes ...

# ------------------ WEBHOOK ROBUSTO (SOLUCIÓN ERROR 500) ------------------

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """
    Maneja el webhook de forma segura evitando reinicializaciones concurrentes
    que causan el error 500 en Render.
    """
    if request.method == 'POST':
        try:
            update_data = request.get_json(force=True)
            if not update_data:
                return 'No data', 400
            
            update = Update.de_json(update_data, application.bot)
            
            async def process_safe():
                # Inicialización "Lazy": Solo si no está listo.
                # Evitamos 'async with' porque cierra la app al terminar.
                if not application._initialized:
                    await application.initialize()
                    await application.start()
                
                await application.process_update(update)
                # No hacemos stop() ni shutdown() para mantenerlo vivo en memoria
            
            # Ejecutar en un nuevo loop aislado para evitar conflictos de hilos de Flask
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(process_safe())
            finally:
                loop.close()
                
            return 'OK', 200
        except Exception as e:
            print(f"🔥 ERROR CRÍTICO WEBHOOK: {e}")
            traceback.print_exc()
            return 'Internal Server Error', 500
            
@flask_app.route('/webhook', methods=['GET'])
def webhook_health():
    return 'Bot is alive 🚀'

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    from waitress import serve
    print(f"Servidor arrancando en puerto {port}...")
    serve(flask_app, host='0.0.0.0', port=port)