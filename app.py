import os
from datetime import datetime, timedelta
from flask import Flask, request, abort
from supabase import create_client, Client
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Carga variables de entorno
from dotenv import load_dotenv
load_dotenv()

# Variables de entorno (en Render las configuras en Environment)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("Faltan variables de entorno: TELEGRAM_TOKEN, SUPABASE_URL o SUPABASE_KEY")

# Cliente Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Flask app
flask_app = Flask(__name__)

# Telegram Application
application = Application.builder().token(TOKEN).build()

# ------------------ Funciones Supabase ------------------

def get_pendientes_por_materia():
    response = supabase.table("estudios").select("materia, tema").eq("tipo", "pendiente").execute()
    pendientes = {}
    for row in response.data:
        materia = row["materia"]
        pendientes.setdefault(materia, []).append(row["tema"])
    return pendientes

def get_estudiados_por_materia():
    response = supabase.table("estudios").select("materia, tema, fecha").eq("tipo", "estudiado").execute()
    estudiados = {}
    for row in response.data:
        materia = row["materia"]
        estudiados.setdefault(materia, []).append((row["tema"], row["fecha"]))
    return estudiados

def get_repasar_hoy():
    hoy = datetime.now().strftime('%Y-%m-%d')
    response = supabase.table("estudios").select("materia, tema").eq("tipo", "repasar").lte("fecha", hoy).execute()
    repasar = {}
    for row in response.data:
        materia = row["materia"]
        repasar.setdefault(materia, []).append(row["tema"])
    return repasar

def add_temas(materia: str, temas: list):
    for tema in temas:
        supabase.table("estudios").insert({"tipo": "pendiente", "materia": materia, "tema": tema}).execute()

def get_materia_de_tema(tema: str, tipo: str = "pendiente"):
    response = supabase.table("estudios").select("materia").eq("tipo", tipo).eq("tema", tema).limit(1).execute()
    if response.data:
        return response.data[0]["materia"]
    return "General"  # Default si no existe

def marcar_estudiado(tema: str):
    hoy = datetime.now().strftime('%Y-%m-%d')
    repaso_fecha = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Obtener materia del pendiente
    materia = get_materia_de_tema(tema, "pendiente")
    
    # Eliminar de pendientes
    supabase.table("estudios").delete().eq("tipo", "pendiente").eq("tema", tema).execute()
    
    # Agregar como estudiado
    supabase.table("estudios").insert({"tipo": "estudiado", "materia": materia, "tema": tema, "fecha": hoy}).execute()
    
    # Agregar repaso
    supabase.table("estudios").insert({"tipo": "repasar", "materia": materia, "tema": tema, "fecha": repaso_fecha}).execute()

def get_calendario():
    response = supabase.table("estudios").select("materia, tema, fecha").eq("tipo", "estudiado").execute()
    cal = {}
    for row in response.data:
        fecha = row["fecha"]
        cal.setdefault(fecha, []).append(f"{row['materia']}: {row['tema']}")
    return cal

def eliminar_tema(tema: str):
    supabase.table("estudios").delete().eq("tema", tema).execute()  # Elimina en todos los tipos

def eliminar_materia(materia: str):
    supabase.table("estudios").delete().eq("materia", materia).execute()  # Elimina todos los registros de la materia

# ------------------ Handlers ------------------

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
    lineas = texto.split('\n')[1:]  # Ignora el comando
    if not lineas:
        await update.message.reply_text('Uso: /agregar_temas materia: NombreMateria\nTema1\nTema2...')
        return
    
    # Parsear materia
    primera_linea = lineas[0].strip()
    if not primera_linea.startswith('materia:'):
        await update.message.reply_text('La primera línea debe ser "materia: NombreMateria"')
        return
    materia = primera_linea.split(':', 1)[1].strip()
    
    # Temas
    temas = [linea.strip() for linea in lineas[1:] if linea.strip()]
    if not temas:
        await update.message.reply_text('Agrega al menos un tema después de la materia.')
        return
    
    add_temas(materia, temas)
    await update.message.reply_text(f'✅ Agregados {len(temas)} temas a la materia "{materia}".')

async def estudiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tema = ' '.join(context.args).strip()
    if tema:
        marcar_estudiado(tema)
        hoy = datetime.now().strftime('%Y-%m-%d')
        repaso_fecha = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        await update.message.reply_text(
            f'🎉 Tema "{tema}" marcado como estudiado el {hoy}.\n'
            f'Repaso programado para el {repaso_fecha}.'
        )
    else:
        await update.message.reply_text('Uso: /estudiar Nombre del tema')

async def pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pendientes = get_pendientes_por_materia()
    if pendientes:
        texto = '📚 Temas pendientes por materia:\n'
        for materia, temas in sorted(pendientes.items()):
            if temas:  # Solo muestra materias con temas
                texto += f'\n{materia}:\n' + '\n'.join(f"• {t}" for t in sorted(temas)) + '\n'
        await update.message.reply_text(texto.strip())
    else:
        await update.message.reply_text('No hay temas pendientes por ahora.')

async def estudiados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    estudiados = get_estudiados_por_materia()
    pendientes = get_pendientes_por_materia()
    
    texto = '✅ Temas estudiados por materia:\n'
    for materia, items in sorted(estudiados.items()):
        if items:
            texto += f'\n{materia}:\n' + '\n'.join(f"• {t} ({f})" for t, f in sorted(items)) + '\n'
    
    if pendientes:
        texto += '\n📚 Temas pendientes por materia:\n'
        for materia, temas in sorted(pendientes.items()):
            if temas:
                texto += f'\n{materia}:\n' + '\n'.join(f"• {t}" for t in sorted(temas)) + '\n'
    
    if texto == '✅ Temas estudiados por materia:\n':
        texto = 'Aún no has marcado temas como estudiados.'
    
    await update.message.reply_text(texto.strip())

async def repasar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repasar = get_repasar_hoy()
    if repasar:
        texto = '🔄 Temas para repasar hoy por materia:\n'
        for materia, temas in sorted(repasar.items()):
            if temas:
                texto += f'\n{materia}:\n' + '\n'.join(f"• {t}" for t in sorted(temas)) + '\n'
        await update.message.reply_text(texto.strip())
    else:
        await update.message.reply_text('¡Nada para repasar hoy! 🎉')

async def calendario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cal = get_calendario()
    if cal:
        texto = '📅 Historial de temas estudiados:\n'
        for fecha in sorted(cal.keys(), reverse=True):
            texto += f"\n{fecha}:\n" + '\n'.join(f"• {t}" for t in sorted(cal[fecha])) + "\n"
        await update.message.reply_text(texto.strip())
    else:
        await update.message.reply_text('Aún no has marcado temas como estudiados.')

async def eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text('Uso: /eliminar tema "Nombre Tema" o /eliminar materia "Nombre Materia"')
        return
    
    tipo = args[0].lower()
    nombre = ' '.join(args[1:]).strip().strip('"')
    
    if tipo == 'tema':
        eliminar_tema(nombre)
        await update.message.reply_text(f'🗑️ Tema "{nombre}" eliminado de todos los registros.')
    elif tipo == 'materia':
        eliminar_materia(nombre)
        await update.message.reply_text(f'🗑️ Materia "{nombre}" eliminada completamente (todos sus temas).')
    else:
        await update.message.reply_text('Tipo inválido: usa "tema" o "materia".')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Usa alguno de los comandos (/start para verlos).')

# Registrar handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("agregar_temas", agregar_temas))
application.add_handler(CommandHandler("estudiar", estudiar))
application.add_handler(CommandHandler("pendientes", pendientes))
application.add_handler(CommandHandler("estudiados", estudiados))
application.add_handler(CommandHandler("repasar", repasar))
application.add_handler(CommandHandler("calendario", calendario))
application.add_handler(CommandHandler("eliminar", eliminar))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# ------------------ Webhook Flask ------------------

@flask_app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return 'Bot is alive 🚀'
    
    if request.method == 'POST':
        try:
            update = Update.de_json(request.get_json(force=True), application.bot)
            if update:
                application.process_update(update)
            return 'OK', 200
        except Exception as e:
            print(f"Error en webhook: {e}")
            return 'Error', 500
    
    abort(400)

# ------------------ Inicio ------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    from waitress import serve
    print(f"Iniciando servidor en puerto {port}...")
    serve(flask_app, host='0.0.0.0', port=port)