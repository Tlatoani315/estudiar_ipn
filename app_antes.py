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

# Telegram Bot
application = Application.builder().token(TOKEN).build()

# ------------------ FUNCIONES BD (LÓGICA) ------------------

def existe_subtema(materia, tema, subtema):
    """Verifica si el subtema ya existe en cualquier estado (pendiente, estudiado, repasar)."""
    # Se asume que la combinación Materia-Tema-Subtema debe ser única en el sistema
    res = supabase.table("estudios").select("id") \
        .eq("materia", materia) \
        .eq("tema", tema) \
        .eq("subtema", subtema) \
        .execute()
    return len(res.data) > 0

def agregar_repaso_siguiente(repasar_row):
    """Calcula la próxima fecha basada en el número de repasos previos (Spaced Repetition)"""
    count = repasar_row.get("repasos_count", 0)
    if count >= 4:
        return # Ya se graduó
    
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

def marcar_estudiado_logica(subtema_input: str):
    """
    Busca por SUBTEMA (ya que los temas completos no se estudian).
    """
    hoy = datetime.now().strftime('%Y-%m-%d')
    
    # 1. ¿Es un REPASO existente (tipo='repasar')?
    # Buscamos coincidencias exactas en subtema
    resp_repaso = supabase.table("estudios").select("*") \
        .eq("tipo", "repasar") \
        .eq("subtema", subtema_input) \
        .lte("fecha", hoy).execute()
    
    if resp_repaso.data:
        row = resp_repaso.data[0]
        # Mover a estudiado (histórico de hoy)
        supabase.table("estudios").insert({
            "tipo": "estudiado",
            "materia": row["materia"],
            "tema": row["tema"],
            "subtema": row["subtema"],
            "fecha": hoy
        }).execute()
        # Borrar el pendiente de repaso
        supabase.table("estudios").delete().eq("id", row["id"]).execute()
        # Programar siguiente repaso
        agregar_repaso_siguiente(row)
        return "Repaso completado", row

    # 2. ¿Es un PENDIENTE (tipo='pendiente')?
    else:
        resp_pendiente = supabase.table("estudios").select("*") \
            .eq("tipo", "pendiente") \
            .eq("subtema", subtema_input).execute()
            
        if resp_pendiente.data:
            row = resp_pendiente.data[0]
            # Borrar de pendientes
            supabase.table("estudios").delete().eq("id", row["id"]).execute()
            
            # Insertar en estudiado (histórico)
            supabase.table("estudios").insert({
                "tipo": "estudiado",
                "materia": row["materia"],
                "tema": row["tema"],
                "subtema": row["subtema"],
                "fecha": hoy
            }).execute()
            
            # Crear primer repaso para mañana
            repaso_fecha = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            supabase.table("estudios").insert({
                "tipo": "repasar",
                "materia": row["materia"],
                "tema": row["tema"],
                "subtema": row["subtema"],
                "fecha": repaso_fecha,
                "repasos_count": 1
            }).execute()
            return "Nuevo tema estudiado", row
            
        else:
            raise Exception("No encontrado en pendientes ni repasos")

# --- Funciones de Lectura/Borrado ---

def get_pendientes_por_materia():
    response = supabase.table("estudios").select("materia, tema, subtema").eq("tipo", "pendiente").execute()
    data = {}
    for row in response.data:
        mat = row["materia"] or "Sin materia"
        tem = row["tema"] or "Sin tema"
        sub = row["subtema"]
        # Solo listar si tiene subtema, ya que es la unidad de estudio
        if sub:
            data.setdefault(mat, {}).setdefault(tem, []).append(sub)
    return data

def get_estudiados_por_materia():
    response = supabase.table("estudios").select("materia, tema, subtema, fecha").eq("tipo", "estudiado").execute()
    data = {}
    for row in response.data:
        mat = row["materia"] or "Sin materia"
        tem = row["tema"] or "Sin tema"
        sub = row["subtema"]
        if sub:
            data.setdefault(mat, {}).setdefault(tem, []).append((sub, row["fecha"]))
    return data

def get_repasar_hoy():
    hoy = datetime.now().strftime('%Y-%m-%d')
    response = supabase.table("estudios").select("materia, tema, subtema").eq("tipo", "repasar").lte("fecha", hoy).execute()
    data = {}
    for row in response.data:
        mat = row["materia"] or "Sin materia"
        tem = row["tema"] or "Sin tema"
        sub = row["subtema"]
        if sub:
            data.setdefault(mat, {}).setdefault(tem, []).append(sub)
    return data

def get_calendario():
    response = supabase.table("estudios").select("materia, tema, subtema, fecha").eq("tipo", "estudiado").execute()
    cal = {}
    for row in response.data:
        fecha = row["fecha"]
        texto = f"{row['materia']}: {row['tema']} → {row['subtema']}"
        cal.setdefault(fecha, []).append(texto)
    return cal

def eliminar_subtema(nombre_subtema: str):
    supabase.table("estudios").delete().eq("subtema", nombre_subtema).execute()

def eliminar_materia(materia: str):
    supabase.table("estudios").delete().eq("materia", materia).execute()

# ------------------ HANDLERS ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '¡Hola! Soy tu bot de estudios (Versión Jerárquica).\n\n'
        'Comandos:\n'
        '/agregar_temas\n materia: M\n tema: T\n subtema: S\n → Agregar estructura\n'
        '/estudiar <subtema> → Marcar subtema como estudiado\n'
        '/pendientes → Ver subtemas pendientes\n'
        '/estudiados → Ver historial\n'
        '/repasar → Ver repasos para hoy\n'
        '/calendario → Ver calendario\n'
        '/eliminar subtema "Nombre" → Eliminar un subtema\n'
        '/eliminar materia "Nombre" → Eliminar materia completa'
    )

async def agregar_temas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    # Separar líneas y eliminar vacías
    lineas = [l.strip() for l in texto.split('\n')[1:] if l.strip()]
    
    current_materia = None
    current_tema = None
    agregados = 0
    ignorados = 0
    
    for linea in lineas:
        low = linea.lower()
        
        # Detector de Materia
        if low.startswith('materia:'):
            current_materia = linea.split(':', 1)[1].strip()
            current_tema = None # Reset tema al cambiar materia
            
        # Detector de Tema
        elif low.startswith('tema:'):
            if not current_materia:
                await update.message.reply_text(f'⚠️ Error: Encontré "tema: {linea}" sin una materia definida antes.')
                return
            current_tema = linea.split(':', 1)[1].strip()
            
        # Detector de Subtema
        elif low.startswith('subtema:'):
            if not current_materia or not current_tema:
                await update.message.reply_text(f'⚠️ Error: Encontré "subtema: {linea}" sin materia o tema definidos.')
                return
            
            subtema_nombre = linea.split(':', 1)[1].strip()
            
            # Verificación de Existencia (Materia > Tema > Subtema)
            if not existe_subtema(current_materia, current_tema, subtema_nombre):
                supabase.table("estudios").insert({
                    "tipo": "pendiente",
                    "materia": current_materia,
                    "tema": current_tema,
                    "subtema": subtema_nombre
                }).execute()
                agregados += 1
            else:
                ignorados += 1

    msg = f'✅ Proceso finalizado.\nAgregados: {agregados}\nYa existían (ignorados): {ignorados}'
    if not current_materia:
        msg = "⚠️ No detecté ninguna materia. Usa el formato:\nmateria: Nombre\ntema: Nombre\nsubtema: Nombre"
    
    await update.message.reply_text(msg)

async def estudiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = ' '.join(context.args).strip()
    if not texto:
        await update.message.reply_text('Uso: /estudiar Subtema1, Subtema2...')
        return
    
    # Asumimos que el usuario ingresa nombres de SUBTEMAS separados por comas
    subtemas_raw = [t.strip() for t in texto.split(',') if t.strip()]
    exitosos = [] 
    mensajes = []
    
    for sub_input in subtemas_raw:
        try:
            msg, row = marcar_estudiado_logica(sub_input)
            exitosos.append(row)
            mensajes.append(f'✅ "{sub_input}": {msg}')
        except Exception as e:
            mensajes.append(f'❌ "{sub_input}": No encontrado en pendientes ni repasos.')
            print(f"Error {sub_input}: {e}")

    await update.message.reply_text("\n".join(mensajes))
    
    if exitosos:
        # Generación de Textos Maestros (Prompts)
        
        # 1. Agrupar Materias para el prompt de Keep
        materias_unicas = sorted(list(set([x["materia"] for x in exitosos])))
        materias_str = ", ".join(materias_unicas)
        
        # Lista de subtemas completados
        subtemas_lista = ", ".join([x["subtema"] for x in exitosos])
        
        texto_keep = f"De las listas que tengo en keep agrega palomita de terminado en la lista [{materias_str}], los temas [{subtemas_lista}]"
        
        # 2. Eventos para el Calendario
        # Formato: Materia: Tema -> Subtema
        eventos_lista = ", ".join([f'{x["materia"]}: {x["tema"]} -> {x["subtema"]}' for x in exitosos])
        texto_cal = f"Agrega en el calendario estos eventos que acaban de pasar hoy, es para tener un registro de lo que estudié hoy: [{eventos_lista}]"


        
        await update.message.reply_text(f"`{texto_keep}`", parse_mode='Markdown')
        await update.message.reply_text(f"`{texto_cal}`", parse_mode='Markdown')
        await update.message.reply_text(f"De estos apuntes: Genera 10-15 tarjetas Anki en formato CSV (Frente;Reverso). Frente: Pregunta/concepto corto. Reverso: Respuesta detallada con ejemplos IPN. deben de ser 10-15 tarjetas por cada subtema, y que sean preguntas que me ayuden a repasar lo que acabo de estudiar.")
        await update.message.reply_text("Puedes copiar estos textos para tus sistemas de organización (Keep, Calendario, Notion, etc.)")

async def pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_pendientes_por_materia()
    if not data:
        await update.message.reply_text('No hay pendientes.')
        return
    
    texto = '📚 Pendientes:\n'
    for mat, temas_dict in sorted(data.items()):
        texto += f'\n📌 {mat}:\n'
        for tem, subs in temas_dict.items():
            texto += f'  🔹 {tem}\n'
            for sub in sorted(subs):
                texto += f'     ▫️ {sub}\n'
    await update.message.reply_text(texto.strip())

async def estudiados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    est = get_estudiados_por_materia()
    
    texto = '✅ Estudiados:\n'
    if not est: texto += " (Nada aún)\n"
    
    for mat, temas_dict in sorted(est.items()):
        texto += f'\n📌 {mat}:\n'
        for tem, items in temas_dict.items():
            texto += f'  🔹 {tem}\n'
            for sub, fecha in items:
                texto += f'     ▪️ {sub} ({fecha})\n'
    
    await update.message.reply_text(texto.strip())

async def repasar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_repasar_hoy()
    if not data:
        await update.message.reply_text('¡Nada para repasar hoy! 🎉')
        return

    texto = '🔄 Repasar HOY:\n'
    for mat, temas_dict in sorted(data.items()):
        texto += f'\n📌 {mat}:\n'
        for tem, subs in temas_dict.items():
            texto += f'  🔹 {tem}\n'
            for sub in sorted(subs):
                texto += f'     ▫️ {sub}\n'
    await update.message.reply_text(texto.strip())

async def calendario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cal = get_calendario()
    if not cal:
        await update.message.reply_text('Calendario vacío.')
        return
    
    texto = '📅 Historial:\n'
    for fecha in sorted(cal.keys(), reverse=True):
        texto += f"\n🗓 {fecha}:\n" + '\n'.join(f" • {t}" for t in sorted(cal[fecha])) + "\n"
    await update.message.reply_text(texto.strip())

async def eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text('Uso: /eliminar subtema "Nombre" o /eliminar materia "Nombre"')
        return
    
    tipo = args[0].lower()
    nombre = ' '.join(args[1:]).strip().strip('"')
    
    if tipo == 'subtema':
        eliminar_subtema(nombre)
        await update.message.reply_text(f'🗑️ Subtema "{nombre}" eliminado.')
    elif tipo == 'materia':
        eliminar_materia(nombre)
        await update.message.reply_text(f'🗑️ Materia "{nombre}" eliminada.')
    else:
        await update.message.reply_text('Usa "subtema" o "materia".')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass 

# Registro de comandos
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("agregar_temas", agregar_temas))
application.add_handler(CommandHandler("estudiar", estudiar))
application.add_handler(CommandHandler("pendientes", pendientes))
application.add_handler(CommandHandler("estudiados", estudiados))
application.add_handler(CommandHandler("repasar", repasar))
application.add_handler(CommandHandler("calendario", calendario))
application.add_handler(CommandHandler("eliminar", eliminar))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# ------------------ WEBHOOK ROBUSTO ------------------

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        try:
            update_data = request.get_json(force=True)
            if not update_data: return 'No data', 400
            
            update = Update.de_json(update_data, application.bot)
            
            async def process_safe():
                if not application._initialized:
                    await application.initialize()
                    await application.start()
                await application.process_update(update)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(process_safe())
            finally:
                loop.close()
            return 'OK', 200
        except Exception as e:
            traceback.print_exc()
            return 'Error', 500

@flask_app.route('/webhook', methods=['GET'])
def webhook_health():
    return 'Bot is alive 🚀'

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    from waitress import serve
    print(f"Iniciando en puerto {port}...")
    serve(flask_app, host='0.0.0.0', port=port)