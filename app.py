import os
from datetime import datetime, timedelta
from flask import Flask, request, abort
from supabase import create_client, Client
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
import traceback

# Carga variables de entorno
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("Faltan variables de entorno")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

flask_app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

# ------------------ FUNCIONES SUPABASE ------------------

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
    response = supabase.table("estudios").select("materia, tema, subtema").eq("tipo", "repasar").lte("fecha", hoy).execute()
    data = {}
    for row in response.data:
        mat = row["materia"] or "Sin materia"
        tem = row["tema"] or "Sin tema"
        sub = row["subtema"]
        data.setdefault(mat, {}).setdefault(tem, []).append(sub)
    return data

def add_subtemas(materia: str, tema: str, subtemas: list):
    for sub in subtemas:
        sub = sub.strip()
        if sub:
            supabase.table("estudios").insert({
                "tipo": "pendiente",
                "materia": materia,
                "tema": tema,
                "subtema": sub
            }).execute()

def get_info_tema(tema: str, tipo: str = "pendiente"):
    response = supabase.table("estudios").select("materia, tema, subtema").eq("tipo", tipo).eq("tema", tema).limit(1).execute()
    if response.data:
        r = response.data[0]
        return r["materia"] or "General", r["tema"], r["subtema"]
    return "General", tema, None

def marcar_estudiado(tema_input: str):
    hoy = datetime.now().strftime('%Y-%m-%d')
    
    # 1. Buscar si es un REPASO pendiente para hoy (o atrasado)
    resp_repaso = supabase.table("estudios").select("*").eq("tipo", "repasar").eq("tema", tema_input).execute()
    
    if resp_repaso.data:
        # ES UN REPASO: Actualizamos al siguiente nivel
        row = resp_repaso.data[0]
        
        # Guardar historial de que se estudió hoy
        supabase.table("estudios").insert({
            "tipo": "estudiado",
            "materia": row["materia"],
            "tema": row["tema"],
            "subtema": row["subtema"],
            "fecha": hoy
        }).execute()
        
        # Borrar el aviso de repaso viejo
        supabase.table("estudios").delete().eq("id", row["id"]).execute() # Asumiendo que Supabase tiene col 'id', si no usa eq match de todo
        
        # Calcular y agendar el SIGUIENTE repaso (Aquí llamamos a tu función olvidada)
        agregar_repaso_siguiente(row)
        return f"Repaso completado. Siguiente nivel programado."

    # 2. Si no es repaso, buscamos si es PENDIENTE
    else:
        materia, tema_real, subtema = get_info_tema(tema_input, "pendiente")
        
        # Si devuelve "General" y el tema input es distinto, es que no existe
        if materia == "General" and tema_real == tema_input:
             # Opcional: Podrías decidir no guardarlo si no existe en pendientes
             pass

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
        
        # Primer repaso (Nivel 1)
        repaso_fecha = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        supabase.table("estudios").insert({
            "tipo": "repasar",
            "materia": materia,
            "tema": tema_real,
            "subtema": subtema,
            "fecha": repaso_fecha,
            "repasos_count": 1
        }).execute()
        
        return "Tema nuevo estudiado. Primer repaso mañana."

def agregar_repaso_siguiente(repasar_row):
    count = repasar_row["repasos_count"]
    if count >= 4:
        return  # No más repasos después del cuarto
    
    dias = [3, 7, 30][count-1]  # 1→+3d, 2→+7d, 3→+30d
    nueva_fecha = (datetime.strptime(repasar_row["fecha"], '%Y-%m-%d') + timedelta(days=dias)).strftime('%Y-%m-%d')
    
    supabase.table("estudios").insert({
        "tipo": "repasar",
        "materia": repasar_row["materia"],
        "tema": repasar_row["tema"],
        "subtema": repasar_row["subtema"],
        "fecha": nueva_fecha,
        "repasos_count": count + 1
    }).execute()

def get_calendario():
    response = supabase.table("estudios").select("materia, tema, subtema, fecha").eq("tipo", "estudiado").execute()
    cal = {}
    for row in response.data:
        fecha = row["fecha"]
        texto = f"{row['materia']}: {row['tema']}"
        if row["subtema"]:
            texto += f" → {row['subtema']}"
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
        'Comandos principales:\n'
        '/agregar_temas → agregar materia/tema/subtemas\n'
        '/estudiar tema1, tema2, tema3 → marcar varios como estudiados\n'
        '/pendientes → ver pendientes por materia/tema\n'
        '/estudiados → estudiados + pendientes\n'
        '/repasar → repasos de hoy\n'
        '/calendario → historial\n'
        '/eliminar tema "Nombre"   o   /eliminar materia "Nombre"'
    )

async def agregar_temas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    lineas = [l.strip() for l in texto.split('\n')[1:] if l.strip()]
    
    if not lineas or not lineas[0].startswith('materia:'):
        await update.message.reply_text(
            'Formato:\n'
            '/agregar_temas\n'
            'materia: Nombre de la Materia\n'
            'tema: Nombre del Tema\n'
            'Subtema 1\n'
            'Subtema 2\n'
            'tema: Otro Tema\n'
            'Subtema A\n'
            'Subtema B'
        )
        return
    
    materia = lineas[0].split(':', 1)[1].strip()
    tema_actual = None
    subtemas = []
    contador = 0
    
    for linea in lineas[1:]:
        if linea.startswith('tema:'):
            if tema_actual and subtemas:
                add_subtemas(materia, tema_actual, subtemas)
                contador += len(subtemas)
            tema_actual = linea.split(':', 1)[1].strip()
            subtemas = []
        elif tema_actual:
            subtemas.append(linea)
    
    if tema_actual and subtemas:
        add_subtemas(materia, tema_actual, subtemas)
        contador += len(subtemas)
    
    if contador > 0:
        await update.message.reply_text(f'✅ Agregados {contador} subtemas en "{materia}".')
    else:
        await update.message.reply_text('No se agregaron subtemas válidos.')

async def estudiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = ' '.join(context.args).strip()
    if not texto:
        await update.message.reply_text('Uso: /estudiar tema1, tema2, tema3')
        return
    
    temas = [t.strip() for t in texto.split(',') if t.strip()]
    resultados = []
    
    for tema in temas:
        try:
            marcar_estudiado(tema)
            resultados.append(f'"{tema}" marcado como estudiado')
        except Exception as e:
            resultados.append(f'Error en "{tema}": {str(e)}')
    
    hoy = datetime.now().strftime('%Y-%m-%d')
    repaso_info = "Primer repaso en 1 día"
    await update.message.reply_text(
        f'🎉 Resultados:\n' + '\n'.join(resultados) + f'\n\n{hoy}\n{repaso_info}'
    )

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
                if sub:
                    texto += f'     → {sub}\n'
                else:
                    texto += '     (sin subtema)\n'
    await update.message.reply_text(texto.strip() or 'No hay pendientes.')

# ... (los demás handlers como estudiados, repasar, calendario, eliminar se mantienen similares, solo actualiza los que usan select para incluir "subtema")

# ------------------ WEBHOOK ------------------

@flask_app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return 'Bot is alive 🚀'
    
    if request.method == 'POST':
        try:
            update_data = request.get_json(force=True)
            if update_data:
                update = Update.de_json(update_data, application.bot)
                if update:
                    async def process():
                        async with application:
                            await application.process_update(update)
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(process())
                    finally:
                        loop.close()
            return 'OK', 200
        except Exception as e:
            print(f"ERROR WEBHOOK: {type(e).__name__}: {str(e)}")
            traceback.print_exc()
            return 'Internal error', 500
    
    abort(400)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    from waitress import serve
    print(f"Iniciando en puerto {port}...")
    serve(flask_app, host='0.0.0.0', port=port)