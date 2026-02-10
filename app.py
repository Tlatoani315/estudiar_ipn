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

def marcar_estudiado_logica(tema_input: str):
    hoy = datetime.now().strftime('%Y-%m-%d')
    
    # 1. ¿Es un REPASO existente?
    resp_repaso = supabase.table("estudios").select("*").eq("tipo", "repasar").eq("tema", tema_input).lte("fecha", hoy).execute()
    
    if resp_repaso.data:
        row = resp_repaso.data[0]
        supabase.table("estudios").insert({
            "tipo": "estudiado",
            "materia": row["materia"],
            "tema": row["tema"],
            "subtema": row["subtema"],
            "fecha": hoy
        }).execute()
        supabase.table("estudios").delete().eq("id", row["id"]).execute()
        agregar_repaso_siguiente(row)
        return "Repaso completado", {"materia": row["materia"], "tema": row["tema"]}

    # 2. Es un TEMA NUEVO
    else:
        materia, tema_real, subtema = get_info_tema(tema_input, "pendiente")
        supabase.table("estudios").delete().eq("tipo", "pendiente").eq("tema", tema_input).execute()
        supabase.table("estudios").insert({
            "tipo": "estudiado",
            "materia": materia,
            "tema": tema_real,
            "subtema": subtema,
            "fecha": hoy
        }).execute()
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

def add_temas_simples(materia, lista_temas):
    for t in lista_temas:
        if t: supabase.table("estudios").insert({"tipo": "pendiente", "materia": materia, "tema": t}).execute()

def add_subtemas(materia, tema, subtemas):
    for sub in subtemas:
        if sub: supabase.table("estudios").insert({"tipo": "pendiente", "materia": materia, "tema": tema, "subtema": sub}).execute()

# --- Funciones de Lectura/Borrado ---

def get_pendientes_por_materia():
    response = supabase.table("estudios").select("materia, tema, subtema").eq("tipo", "pendiente").execute()
    data = {}
    for row in response.data:
        mat = row["materia"] or "Sin materia"
        tem = row["tema"] or "Sin tema"
        sub = row["subtema"]
        data.setdefault(mat, {}).setdefault(tem, []).append(sub)
    return data

def get_estudiados_por_materia():
    response = supabase.table("estudios").select("materia, tema, subtema, fecha").eq("tipo", "estudiado").execute()
    data = {}
    for row in response.data:
        mat = row["materia"] or "Sin materia"
        tem = row["tema"] or "Sin tema"
        sub = row["subtema"]
        data.setdefault(mat, {}).setdefault(tem, []).append((sub, row["fecha"]))
    return data

def get_repasar_hoy():
    hoy = datetime.now().strftime('%Y-%m-%d')
    # lte = less than or equal (hoy o atrasados)
    response = supabase.table("estudios").select("materia, tema, subtema").eq("tipo", "repasar").lte("fecha", hoy).execute()
    data = {}
    for row in response.data:
        mat = row["materia"] or "Sin materia"
        tem = row["tema"] or "Sin tema"
        sub = row["subtema"]
        data.setdefault(mat, {}).setdefault(tem, []).append(sub)
    return data

def get_calendario():
    response = supabase.table("estudios").select("materia, tema, subtema, fecha").eq("tipo", "estudiado").execute()
    cal = {}
    for row in response.data:
        fecha = row["fecha"]
        texto = f"{row['materia']}: {row['tema']}"
        if row["subtema"]: texto += f" → {row['subtema']}"
        cal.setdefault(fecha, []).append(texto)
    return cal

def eliminar_tema(tema: str):
    supabase.table("estudios").delete().eq("tema", tema).execute()

def eliminar_materia(materia: str):
    supabase.table("estudios").delete().eq("materia", materia).execute()

# ------------------ HANDLERS ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '¡Hola! Soy tu bot de estudios.\n\n'
        'Comandos:\n'
        '/agregar_temas materia: NombreMateria\nTema1\nTema2 → Agregar temas a materia\n'
        '/estudiar <tema> → Marcar como estudiado\n'
        '/pendientes → Ver temas pendientes por materia\n'
        '/estudiados → Ver estudiados por materia + pendientes al final\n'
        '/repasar → Ver temas para repasar hoy por materia\n'
        '/calendario → Ver historial de temas estudiados\n'
        '/eliminar tema "Nombre Tema" → Eliminar un tema\n'
        '/eliminar materia "Nombre Materia" → Eliminar una materia entera'
    )

async def agregar_temas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    lineas = [l.strip() for l in texto.split('\n')[1:] if l.strip()]
    
    if not lineas or not lineas[0].lower().startswith('materia:'):
        await update.message.reply_text('⚠️ Falta la materia.\nUso:\n/agregar_temas\nmateria: Matemáticas\nTema 1\nTema 2')
        return
    
    materia = lineas[0].split(':', 1)[1].strip()
    tema_actual = None
    subtemas = []
    temas_simples = []
    contador = 0
    
    for linea in lineas[1:]:
        if linea.lower().startswith('tema:'):
            if tema_actual and subtemas:
                add_subtemas(materia, tema_actual, subtemas)
                contador += len(subtemas)
                subtemas = []
            elif temas_simples:
                add_temas_simples(materia, temas_simples)
                contador += len(temas_simples)
                temas_simples = []
            tema_actual = linea.split(':', 1)[1].strip()
        else:
            if tema_actual: subtemas.append(linea)
            else: temas_simples.append(linea)
    
    if tema_actual and subtemas:
        add_subtemas(materia, tema_actual, subtemas)
        contador += len(subtemas)
    elif temas_simples:
        add_temas_simples(materia, temas_simples)
        contador += len(temas_simples)
    
    await update.message.reply_text(f'✅ Agregados {contador} elementos a "{materia}".')

async def estudiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = ' '.join(context.args).strip()
    if not texto:
        await update.message.reply_text('Uso: /estudiar Tema1, Tema2...')
        return
    
    temas_raw = [t.strip() for t in texto.split(',') if t.strip()]
    exitosos = [] 
    mensajes = []
    
    for tema in temas_raw:
        try:
            msg, info = marcar_estudiado_logica(tema)
            exitosos.append(info)
            mensajes.append(f'✅ "{tema}": {msg}')
        except Exception as e:
            mensajes.append(f'❌ Error en "{tema}": No encontrado o error interno.')
            print(f"Error {tema}: {e}")

    await update.message.reply_text("\n".join(mensajes))
    
    if exitosos:
        materias_str = ", ".join(sorted(list(set([x["materia"] for x in exitosos]))))
        temas_lista = ", ".join([x["tema"] for x in exitosos])
        texto_keep = f"De las listas que tengo en keep agrega palomita de terminado en la lista [{materias_str}], los temas [{temas_lista}]"
        
        eventos_lista = ", ".join([f'{x["materia"]}:{x["tema"]}' for x in exitosos])
        texto_cal = f"Agrega en el calendario estos eventos que acaban de pasar hoy, es para tener un registro de lo que estudié hoy: [{eventos_lista}]"
        
        await update.message.reply_text(f"`{texto_keep}`", parse_mode='Markdown')
        await update.message.reply_text(f"`{texto_cal}`", parse_mode='Markdown')

async def pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_pendientes_por_materia()
    if not data:
        await update.message.reply_text('No hay pendientes.')
        return
    
    texto = '📚 Pendientes:\n'
    for mat, temas_dict in sorted(data.items()):
        texto += f'\n{mat}:\n'
        for tem, subs in temas_dict.items():
            texto += f'  • {tem}\n'
            for sub in sorted(subs):
                if sub: texto += f'     → {sub}\n'
    await update.message.reply_text(texto.strip())

async def estudiados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    est = get_estudiados_por_materia()
    pen = get_pendientes_por_materia()
    
    texto = '✅ Estudiados:\n'
    if not est: texto += " (Nada aún)\n"
    
    for mat, temas_dict in sorted(est.items()):
        texto += f'\n{mat}:\n'
        for tem, items in temas_dict.items():
            texto += f'  • {tem}\n'
            for sub, fecha in items:
                if sub: texto += f'     → {sub} ({fecha})\n'
                else: texto += f'     (General) ({fecha})\n'

    if pen:
        texto += '\n📚 Pendientes (Resumen):\n'
        for mat in sorted(pen.keys()):
            texto += f'• {mat}: {len(pen[mat])} temas\n'
    
    await update.message.reply_text(texto.strip())

async def repasar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_repasar_hoy()
    if not data:
        await update.message.reply_text('¡Nada para repasar hoy! 🎉')
        return

    texto = '🔄 Repasar HOY:\n'
    for mat, temas_dict in sorted(data.items()):
        texto += f'\n{mat}:\n'
        for tem, subs in temas_dict.items():
            texto += f'  • {tem}\n'
            for sub in sorted(subs):
                if sub: texto += f'     → {sub}\n'
    await update.message.reply_text(texto.strip())

async def calendario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cal = get_calendario()
    if not cal:
        await update.message.reply_text('Calendario vacío.')
        return
    
    texto = '📅 Historial:\n'
    for fecha in sorted(cal.keys(), reverse=True):
        texto += f"\n{fecha}:\n" + '\n'.join(f"• {t}" for t in sorted(cal[fecha])) + "\n"
    await update.message.reply_text(texto.strip())

async def eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text('Uso: /eliminar tema "Nombre" o /eliminar materia "Nombre"')
        return
    
    tipo = args[0].lower()
    nombre = ' '.join(args[1:]).strip().strip('"')
    
    if tipo == 'tema':
        eliminar_tema(nombre)
        await update.message.reply_text(f'🗑️ Tema "{nombre}" eliminado.')
    elif tipo == 'materia':
        eliminar_materia(nombre)
        await update.message.reply_text(f'🗑️ Materia "{nombre}" eliminada.')
    else:
        await update.message.reply_text('Usa "tema" o "materia".')

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