# src/handlers.py
from telegram import Update
from telegram.ext import ContextTypes
from .database import db
from .services import SpacedRepetitionService
from datetime import datetime

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🤖 **Bot de Estudios 2.0**\n\n'
        '**Comandos:**\n'
        '`/agregar_temas` (Materia/Tema/Subtema)\n'
        '`/estudiar_temas <Materia> <Num>` (Dame N temas nuevos)\n'
        '`/estudiar <Subtema>` (Registrar estudio hoy)\n'
        '`/dominado <Subtema>` (¡Ya me lo sé!)\n'
        '`/repasar` (Lo que toca hoy)\n'
        '`/temasFaltantes` (Métricas globales)\n'
        '`/materias_metricas` (Detalle por materia)\n'
        '`/eliminar subtema "Nombre"`',
        parse_mode='Markdown'
    )

async def agregar_temas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nuevo formato: Materia/Tema/Subtema"""
    texto = update.message.text.strip()
    # Ignoramos la primera línea si es el comando
    lineas = [l.strip() for l in texto.split('\n') if '/' in l]
    
    agregados = 0
    ignorados = 0
    errores = 0

    for linea in lineas:
        partes = linea.split('/')
        if len(partes) < 3:
            errores += 1
            continue
        
        # Asumimos Materia/Tema/Subtema (pueden haber mas slashes, unimos el resto)
        mat = partes[0].strip()
        tem = partes[1].strip()
        sub = "/".join(partes[2:]).strip() # Por si el subtema tiene slashes
        
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

    await update.message.reply_text(
        f"📥 **Procesado:**\n✅ Agregados: {agregados}\n⏭ Ignorados (repetidos): {ignorados}\n⚠️ Errores formato: {errores}\n\n"
        "Recuerda el formato:\n`Materia/Tema/Subtema`",
        parse_mode='Markdown'
    )

async def estudiar_temas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elige N temas al azar de una materia."""
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Uso: `/estudiar_temas <NombreMateria> <Cantidad>`", parse_mode='Markdown')
        return

    # Manejar nombres de materia con espacios. El último arg es la cantidad.
    cantidad_str = args[-1]
    materia = " ".join(args[:-1])

    if not cantidad_str.isdigit():
        await update.message.reply_text("❌ La cantidad debe ser un número.")
        return
    
    cantidad = int(cantidad_str)
    sugerencias = SpacedRepetitionService.sugerir_nuevos_temas(materia, cantidad)

    if not sugerencias:
        await update.message.reply_text(f"🎉 No hay temas pendientes en **{materia}**.", parse_mode='Markdown')
        return

    msg = f"🎲 **Temas sugeridos para {materia}:**\n"
    for item in sugerencias:
        msg += f"👉 `{item['materia']} -> {item['tema']} -> {item['subtema']}`\n"
    
    msg += "\nCopia y pega en `/estudiar` cuando termines."
    await update.message.reply_text(msg, parse_mode='Markdown')

async def repasar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hoy = datetime.now().strftime('%Y-%m-%d')
    repasos = db.obtener_repasos_para_fecha(hoy)
    
    if not repasos:
        await update.message.reply_text("✅ ¡Estás al día! No hay repasos pendientes para hoy.")
        return

    # Agrupar
    data = {}
    for r in repasos:
        data.setdefault(r["materia"], []).append(r["subtema"])

    msg = "🔄 **Temas para Repasar HOY:**\n"
    count_total = 0
    for mat, subs in data.items():
        msg += f"\n📌 **{mat}**\n"
        for s in subs:
            msg += f"   ▫️ {s}\n"
            count_total += 1
            
    msg += f"\nTotal: {count_total} subtemas."
    await update.message.reply_text(msg, parse_mode='Markdown')

async def estudiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = ' '.join(context.args).strip()
    if not texto:
        await update.message.reply_text('❌ Uso: `/estudiar Subtema1, Subtema2...`', parse_mode='Markdown')
        return
    
    subtemas = [t.strip() for t in texto.split(',') if t.strip()]
    exitosos = []
    msgs = []

    await update.message.reply_text("⏳ Procesando estudios...")

    for sub in subtemas:
        try:
            msg_res, row = SpacedRepetitionService.procesar_estudio(sub)
            exitosos.append(row)
            msgs.append(f"✅ {sub}: {msg_res}")
        except ValueError:
            msgs.append(f"⚠️ {sub}: No encontrado (¿Check ortografía?)")
        except Exception as e:
            msgs.append(f"❌ {sub}: Error {e}")

    await update.message.reply_text("\n".join(msgs))

    if exitosos:
        materias = sorted(list(set([x["materia"] for x in exitosos])))
        subtemas_str = ", ".join([x["subtema"] for x in exitosos])
        
        # PROMPTS
        p_keep = f"`De las listas que tengo en keep agrega palomita de terminado en la lista [{', '.join(materias)}], los temas [{subtemas_str}]`"
        
        eventos_cal = ", ".join([f'{x["materia"]}: {x["tema"]} -> {x["subtema"]}' for x in exitosos])
        p_cal = f"`Agrega en el calendario estos eventos que acaban de pasar hoy, es para tener un registro de lo que estudié hoy: [{eventos_cal}]`"
        
        p_anki = "De estos apuntes: Genera 10-15 tarjetas Anki en formato CSV..."

        await update.message.reply_text(p_keep, parse_mode='Markdown')
        await update.message.reply_text(p_cal, parse_mode='Markdown')
        await update.message.reply_text(p_anki)

async def dominado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = ' '.join(context.args).strip()
    if not texto:
        await update.message.reply_text('❌ Uso: `/dominado Tema1, Tema2...`', parse_mode='Markdown')
        return

    # AHORA SOPORTA MÚLTIPLES SEPARADOS POR COMA
    subtemas = [t.strip() for t in texto.split(',') if t.strip()]
    msgs = []

    for sub in subtemas:
        if db.marcar_como_dominado(sub):
            msgs.append(f"🏆 **{sub}**: ¡Dominado! (Archivado)")
        else:
            msgs.append(f"⚠️ **{sub}**: No encontrado o ya estaba dominado.")

    await update.message.reply_text("\n".join(msgs), parse_mode='Markdown')

    
async def metricas_globales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /temasFaltantes
    faltantes X/Total - estudiados Y/Total - dominados Z/Total
    """
    regs = db.obtener_todos_registros()
    if not regs:
        await update.message.reply_text("📭 Base de datos vacía.")
        return

    # Usamos un Set para contar Subtemas ÚNICOS, ya que 'estudiado' crea duplicados en historial
    # Pero para el estado actual, filtramos por 'tipo'.
    # Ojo: 'estudiado' es historial. 'pendiente', 'repasar', 'dominado' son estados actuales únicos por subtema.
    
    # 1. Identificar universo de subtemas únicos
    # Mapa: (Materia, Tema, Subtema) -> Estado Actual
    # Prioridad de estado: Dominado > Repasar > Pendiente > (Si solo está en Estudiado es raro, asumimos Repasar perdido o error)
    
    # Simpler approach: Count current status rows
    pendientes = 0
    repasar = 0
    dominados = 0
    
    # Para saber el total REAL, necesitamos agrupar por subtema único
    subtemas_unicos = set()
    
    for r in regs:
        key = f"{r['materia']}|{r['subtema']}"
        subtemas_unicos.add(key)
        
        t = r['tipo']
        if t == 'pendiente': pendientes += 1
        elif t == 'repasar': repasar += 1
        elif t == 'dominado': dominados += 1
        # 'estudiado' es log, no suma al estado actual
    
    # Total de subtemas en el sistema (activos)
    # Nota: Un subtema puede tener log 'estudiado' y estar en 'repasar'.
    # El conteo exacto se basa en los registros de estado (pendiente, repasar, dominado).
    total_activos = pendientes + repasar + dominados
    
    # "Estudiados" según tu fórmula: (repasar + dominados) ? O solo logs?
    # Tu ejemplo: "estudiados 13/144". Asumiré que es (Total - Pendientes) = Progreso.
    progreso = total_activos - pendientes
    
    msg = (
        f"📊 **Estado Global**\n"
        f"Total Subtemas: {total_activos}\n\n"
        f"🔴 Faltantes: {pendientes}/{total_activos} ({(pendientes/total_activos)*100:.1f}%)\n"
        f"🟡 En Progreso (Repaso): {repasar}/{total_activos}\n"
        f"🟢 Dominados: {dominados}/{total_activos}\n\n"
        f"🏁 **Avance Total:** {progreso}/{total_activos}"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def metricas_materia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /materias_metricas
    Formato: materia 33/133 (subtemas vistos/total) 12/24 (temas vistos/total)
    """
    regs = db.obtener_todos_registros()
    if not regs: return

    # Estructura: Materia -> { TemasSet, SubtemasTotal, SubtemasVistos }
    stats = {}

    for r in regs:
        mat = r['materia']
        tem = r['tema']
        sub = r['subtema']
        tipo = r['tipo']

        if mat not in stats:
            stats[mat] = {
                'temas_total': set(),
                'temas_con_pendientes': set(), 
                'subtemas_total_set': set(),
                'subtemas_vistos_set': set() # No pendientes
            }
        
        # Ignorar logs históricos para el conteo de estructura, usar estados actuales si es posible
        # Pero como 'estudiado' es solo log, nos basamos en:
        # Si existe registro 'pendiente' -> No visto.
        # Si existe registro 'repasar' o 'dominado' -> Visto.
        
        if tipo != 'estudiado':
            stats[mat]['temas_total'].add(tem)
            stats[mat]['subtemas_total_set'].add(sub)
            
            if tipo == 'pendiente':
                stats[mat]['temas_con_pendientes'].add(tem)
            else:
                stats[mat]['subtemas_vistos_set'].add(sub)

    msg = "📈 **Métricas por Materia**\n\n"
    
    for mat, data in stats.items():
        total_sub = len(data['subtemas_total_set'])
        # Vistos son Total - Pendientes (Calculado mejor iterando status)
        # Hacemos una corrección rápida: iteramos los registros de nuevo para contar pendientes exactos por materia
        # (Esto se puede optimizar, pero funciona).
        
        pendientes_count = 0
        temas_pendientes = set()
        for r in regs:
            if r['materia'] == mat and r['tipo'] == 'pendiente':
                pendientes_count += 1
                temas_pendientes.add(r['tema'])
        
        vistos_sub = total_sub - pendientes_count
        
        total_temas = len(data['temas_total'])
        temas_vistos = total_temas - len(temas_pendientes)
        
        msg += f"**{mat}**\n"
        msg += f"   Subtemas: {vistos_sub}/{total_sub}\n"
        msg += f"   Temas: {temas_vistos}/{total_temas}\n\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤔 No entendí ese comando.\n"
        "Escribiste algo que no es una instrucción válida o el bot no la escuchó bien.\n"
        "Prueba `/start` para ver la lista."
    )