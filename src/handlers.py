from telegram import Update
from telegram.ext import ContextTypes
from .database import db
from .services import SpacedRepetitionService

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía el mensaje de bienvenida con la lista de comandos."""
    await update.message.reply_text(
        '¡Hola! Soy tu bot de estudios (Versión Modular).\n\n'
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
    """Parsea el mensaje del usuario para agregar múltiples temas a la BD."""
    texto = update.message.text.strip()
    lineas = [l.strip() for l in texto.split('\n')[1:] if l.strip()]
    
    current_materia = None
    current_tema = None
    stats = {"agregados": 0, "ignorados": 0}
    
    for linea in lineas:
        low = linea.lower()
        
        if low.startswith('materia:'):
            current_materia = linea.split(':', 1)[1].strip()
            current_tema = None
        elif low.startswith('tema:'):
            if not current_materia:
                await update.message.reply_text(f'⚠️ Error: "tema: {linea}" sin materia definida.')
                return
            current_tema = linea.split(':', 1)[1].strip()
        elif low.startswith('subtema:'):
            if not current_materia or not current_tema:
                await update.message.reply_text(f'⚠️ Error: "subtema: {linea}" sin jerarquía completa.')
                return
            
            subtema = linea.split(':', 1)[1].strip()
            
            if not db.existe_subtema(current_materia, current_tema, subtema):
                db.insertar_registro({
                    "tipo": "pendiente",
                    "materia": current_materia,
                    "tema": current_tema,
                    "subtema": subtema
                })
                stats["agregados"] += 1
            else:
                stats["ignorados"] += 1

    msg = f'✅ Proceso finalizado.\nAgregados: {stats["agregados"]}\nIgnorados: {stats["ignorados"]}'
    if not current_materia:
        msg = "⚠️ Formato incorrecto. Usa:\nmateria: X\ntema: Y\nsubtema: Z"
    
    await update.message.reply_text(msg)

async def estudiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa una lista de subtemas estudiados y genera prompts de productividad."""
    texto = ' '.join(context.args).strip()
    if not texto:
        await update.message.reply_text('Uso: /estudiar Subtema1, Subtema2...')
        return
    
    subtemas = [t.strip() for t in texto.split(',') if t.strip()]
    exitosos = []
    mensajes = []
    
    for sub in subtemas:
        try:
            msg, row = SpacedRepetitionService.procesar_estudio(sub)
            exitosos.append(row)
            mensajes.append(f'✅ "{sub}": {msg}')
        except ValueError:
            mensajes.append(f'❌ "{sub}": No encontrado en pendientes/repasos.')
        except Exception as e:
            mensajes.append(f'❌ Error interno en "{sub}": {str(e)}')

    await update.message.reply_text("\n".join(mensajes))
    
    if exitosos:
        # Generación de prompts para herramientas externas
        materias = ", ".join(sorted(list(set([x["materia"] for x in exitosos]))))
        temas = ", ".join([x["subtema"] for x in exitosos])
        eventos = ", ".join([f'{x["materia"]}: {x["tema"]} -> {x["subtema"]}' for x in exitosos])
        
        prompts = [
            f"`De las listas que tengo en keep agrega palomita de terminado en la lista [{materias}], los temas [{temas}]`",
            f"`Agrega en el calendario estos eventos que acaban de pasar hoy: [{eventos}]`",
            "De estos apuntes: Genera 10-15 tarjetas Anki en formato CSV..."
        ]
        
        for p in prompts:
            await update.message.reply_text(p, parse_mode='Markdown')

async def pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista los temas pendientes agrupados jerárquicamente."""
    raw_data = db.obtener_pendientes()
    if not raw_data:
        await update.message.reply_text('No hay pendientes.')
        return
        
    # Agrupación de datos para visualización
    data = {}
    for r in raw_data:
        if r["subtema"]:
            data.setdefault(r["materia"] or "?", {}).setdefault(r["tema"] or "?", []).append(r["subtema"])
            
    texto = '📚 Pendientes:\n'
    for mat, temas in sorted(data.items()):
        texto += f'\n📌 {mat}:\n'
        for tem, subs in temas.items():
            texto += f'  🔹 {tem}\n'
            for s in sorted(subs):
                texto += f'     ▫️ {s}\n'
    
    await update.message.reply_text(texto.strip())

# ... (Implementar lógica similar para 'estudiados', 'repasar', 'calendario', 'eliminar' usando db methods)
# Por brevedad, se asume que siguen el mismo patrón de llamar a db.obtener_... y formatear.

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass