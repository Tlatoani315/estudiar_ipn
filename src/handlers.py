# src/handlers.py
from telegram import Update
from telegram.ext import ContextTypes
from .database import db
from .services import SpacedRepetitionService
from datetime import datetime
import traceback

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🤖 **Bot de Estudios (Fixed)**\nUsa /start para ver comandos completos.',
        parse_mode='Markdown'
    )

async def agregar_temas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    lineas = [l.strip() for l in texto.split('\n') if '/' in l]
    
    agregados = 0
    ignorados = 0
    errores = 0

    for linea in lineas:
        partes = linea.split('/')
        if len(partes) < 3:
            errores += 1
            continue
        
        mat = partes[0].strip()
        tem = partes[1].strip()
        sub = "/".join(partes[2:]).strip() 
        
        try:
            if not db.existe_subtema(mat, tem, sub):
                db.insertar_registro({
                    "tipo": "pendiente",
                    "materia": mat,
                    "tema": tem,
                    "subtema": sub
                })
                agregados += 1
            else:
                ignorados += 1
        except Exception:
            traceback.print_exc()
            errores += 1

    await update.message.reply_text(
        f"📥 **Procesado:**\n✅ Agregados: {agregados}\n⏭ Repetidos: {ignorados}\n⚠️ Errores: {errores}",
        parse_mode='Markdown'
    )

async def estudiar_temas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Uso: `/estudiar_temas <Materia> <Cantidad>`", parse_mode='Markdown')
        return

    cantidad_str = args[-1]
    materia = " ".join(args[:-1])

    if not cantidad_str.isdigit():
        await update.message.reply_text("❌ La cantidad debe ser un número.")
        return
    
    try:
        sugerencias = SpacedRepetitionService.sugerir_nuevos_temas(materia, int(cantidad_str))
        if not sugerencias:
            await update.message.reply_text(f"🎉 No hay temas pendientes en **{materia}**.", parse_mode='Markdown')
            return

        msg = f"🎲 **{len(sugerencias)} temas sugeridos para {materia}:**\n"
        for item in sugerencias:
            msg += f"👉 `{item['materia']} -> {item['tema']} -> {item['subtema']}`\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Error: {e}")

async def repasar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hoy = datetime.now().strftime('%Y-%m-%d')
    try:
        repasos = db.obtener_repasos_para_fecha(hoy)
        if not repasos:
            await update.message.reply_text("✅ ¡Estás al día! No hay repasos para hoy.")
            return

        data = {}
        for r in repasos:
            data.setdefault(r["materia"], []).append(r["subtema"])

        msg = "🔄 **Repasar HOY:**\n"
        for mat, subs in data.items():
            msg += f"\n📌 **{mat}**\n"
            for s in subs:
                msg += f"   ▫️ {s}\n"
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Error: {e}")

async def estudiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = ' '.join(context.args).strip()
    if not texto:
        await update.message.reply_text('❌ Uso: `/estudiar Subtema1, Subtema2...`', parse_mode='Markdown')
        return
    
    subtemas = [t.strip() for t in texto.split(',') if t.strip()]
    exitosos = []
    msgs = []

    await update.message.reply_text("⏳ Procesando...")

    for sub in subtemas:
        try:
            msg_res, row = SpacedRepetitionService.procesar_estudio(sub)
            exitosos.append(row)
            msgs.append(f"✅ {sub}: {msg_res}")
        except ValueError:
            msgs.append(f"⚠️ {sub}: No encontrado en pendientes/repaso.")
        except Exception as e:
            traceback.print_exc()
            msgs.append(f"❌ {sub}: Error ({str(e)})")

    await update.message.reply_text("\n".join(msgs))

    if exitosos:
        materias = sorted(list(set([x["materia"] for x in exitosos])))
        subtemas_str = ", ".join([x["subtema"] for x in exitosos])
        eventos = ", ".join([f'{x["materia"]}: {x["tema"]} -> {x["subtema"]}' for x in exitosos])
        
        await update.message.reply_text(f"`De las listas que tengo en keep agrega palomita de terminado en la lista [{', '.join(materias)}], los temas [{subtemas_str}]`", parse_mode='Markdown')
        await update.message.reply_text(f"`Agrega en el calendario estos eventos que acaban de pasar hoy: [{eventos}]`", parse_mode='Markdown')
        await update.message.reply_text("De estos apuntes: Genera tarjetas Anki...")

async def dominado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = ' '.join(context.args).strip()
    if not texto:
        await update.message.reply_text('❌ Uso: `/dominado Subtema`', parse_mode='Markdown')
        return

    subtemas = [t.strip() for t in texto.split(',') if t.strip()]
    msgs = []

    for sub in subtemas:
        try:
            if db.marcar_como_dominado(sub):
                msgs.append(f"🏆 **{sub}**: ¡Dominado!")
            else:
                msgs.append(f"⚠️ **{sub}**: No encontrado.")
        except Exception as e:
            traceback.print_exc()
            msgs.append(f"❌ {sub}: Error ({e})")

    await update.message.reply_text("\n".join(msgs), parse_mode='Markdown')

async def metricas_globales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        regs = db.obtener_todos_registros()
        if not regs:
            await update.message.reply_text("📭 Base vacía.")
            return

        pendientes = sum(1 for r in regs if r['tipo'] == 'pendiente')
        repasar = sum(1 for r in regs if r['tipo'] == 'repasar')
        dominados = sum(1 for r in regs if r['tipo'] == 'dominado')
        
        msg = f"📊 **Estado Global**\n🔴 Pendientes: {pendientes}\n🟡 Repasar: {repasar}\n🟢 Dominados: {dominados}"
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def metricas_materia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        regs = db.obtener_todos_registros()
        if not regs: return

        stats = {}
        for r in regs:
            mat = r['materia']
            if r['tipo'] != 'estudiado': 
                if mat not in stats: stats[mat] = {'total': 0, 'vistos': 0}
                stats[mat]['total'] += 1
                if r['tipo'] in ['repasar', 'dominado']:
                    stats[mat]['vistos'] += 1

        msg = "📈 **Avance por Materia**\n\n"
        for mat, s in stats.items():
            msg += f"**{mat}**: {s['vistos']}/{s['total']} temas\n"

        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text('Uso: /eliminar subtema "Nombre" (o materia)')
        return
    
    tipo = args[0].lower()
    nombre = ' '.join(args[1:]).strip().strip('"')
    
    try:
        if tipo == 'subtema':
            db.eliminar_por_campo("subtema", nombre)
            await update.message.reply_text(f'🗑️ Subtema "{nombre}" eliminado.')
        elif tipo == 'materia':
            db.eliminar_por_campo("materia", nombre)
            await update.message.reply_text(f'🗑️ Materia "{nombre}" eliminada.')
        else:
            await update.message.reply_text('⚠️ Tipo desconocido.')
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def listar_materias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        materias = db.obtener_materias_unicas()
        msg = "📚 **Materias:**\n" + "\n".join([f"🔹 `{m}`" for m in materias])
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
         await update.message.reply_text(f"Error: {e}")

async def listar_temario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("❌ Uso: `/temario <Materia>`")
        return
    materia = " ".join(args).strip()
    
    try:
        registros = db.obtener_detalle_materia(materia)
        if not registros:
            await update.message.reply_text(f"⚠️ Sin datos para {materia}.")
            return
            
        estructura = {}
        for r in registros:
            tema = r['tema']
            sigla = {"pendiente": "(p)", "repasar": "(e)", "dominado": "(d)"}.get(r['tipo'], "(?)")
            estructura.setdefault(tema, []).append((r['subtema'], sigla))

        msg = f"📂 **{materia}**\n"
        for tema in sorted(estructura.keys()):
            msg += f"\n📌 {tema}\n"
            for sub, sigla in sorted(estructura[tema]):
                msg += f"   ▫️ {sub} {sigla}\n"
                
        await update.message.reply_text(msg[:4000], parse_mode='Markdown')
    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"Error: {e}")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤔 No entendí.")