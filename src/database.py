# src/database.py
from supabase import create_client, Client
from typing import List, Dict, Any, Optional
import random
from .config import settings

class DatabaseManager:
    def __init__(self):
        self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.table = self.client.table("estudios")

    # --- Verificaciones ---
    def existe_subtema(self, materia: str, tema: str, subtema: str) -> bool:
        res = self.table.select("id").eq("materia", materia).eq("tema", tema).eq("subtema", subtema).execute()
        return len(res.data) > 0

    # --- Inserción / Actualización ---
    def insertar_registro(self, data: Dict[str, Any]) -> None:
        self.table.insert(data).execute()

    def marcar_como_dominado(self, subtema: str) -> bool:
        """Cambia el estado de un subtema a 'dominado' y borra rastro de repasos pendientes."""
        # 1. Buscar si existe en repasos o pendientes
        res = self.table.select("*").eq("subtema", subtema).neq("tipo", "estudiado").execute()
        
        if not res.data:
            # Quizás ya está dominado o no existe
            return False

        # Eliminamos registros viejos (pendientes o repasos activos)
        for row in res.data:
            self.table.delete().eq("id", row['id']).execute()

        # Insertamos como dominado (usamos fecha hoy como referencia)
        from datetime import datetime
        hoy = datetime.now().strftime('%Y-%m-%d')
        self.insertar_registro({
            "tipo": "dominado",
            "materia": res.data[0]['materia'],
            "tema": res.data[0]['tema'],
            "subtema": subtema,
            "fecha": hoy
        })
        return True

    def eliminar_por_id(self, registro_id: int) -> None:
        self.table.delete().eq("id", registro_id).execute()

    def eliminar_por_campo(self, campo: str, valor: str) -> None:
        self.table.delete().eq(campo, valor).execute()

    # --- Consultas de Estudio ---
    def obtener_pendientes_materia(self, materia: str) -> List[Dict[str, Any]]:
        """Obtiene pendientes de una materia específica."""
        return self.table.select("*").eq("tipo", "pendiente").eq("materia", materia).execute().data

    def obtener_pendientes(self) -> List[Dict[str, Any]]:
        return self.table.select("*").eq("tipo", "pendiente").execute().data

    def obtener_repasos_para_fecha(self, fecha_limite: str) -> List[Dict[str, Any]]:
        # Busca repasos programados para hoy o antes (atrasados) que NO estén dominados
        return self.table.select("*").eq("tipo", "repasar").lte("fecha", fecha_limite).execute().data

    def buscar_repaso_especifico(self, subtema: str) -> Optional[Dict[str, Any]]:
        # Busca en 'repasar' sin importar fecha, para marcarlo estudiado si el usuario quiere adelantarse
        res = self.table.select("*").eq("tipo", "repasar").eq("subtema", subtema).execute()
        return res.data[0] if res.data else None

    def buscar_pendiente_especifico(self, subtema: str) -> Optional[Dict[str, Any]]:
        res = self.table.select("*").eq("tipo", "pendiente").eq("subtema", subtema).execute()
        return res.data[0] if res.data else None

    # --- Métricas y Consultas Masivas ---
    def obtener_todos_registros(self) -> List[Dict[str, Any]]:
        """Trae todo para calcular métricas en memoria (más eficiente que mil selects si la DB es pequeña < 10k rows)"""
        # Nota: Supabase tiene límite de filas por request (usualmente 1000). 
        # Si tienes muchos datos, deberás paginar. Para uso personal, esto sirve.
        return self.table.select("materia, tema, subtema, tipo").execute().data

    def obtener_materias_unicas(self) -> List[str]:
        """Devuelve una lista ordenada de todas las materias existentes."""
        # Traemos todo y filtramos en Python (eficiente para <10k registros)
        res = self.table.select("materia").execute()
        if not res.data:
            return []
        # Usamos set para eliminar duplicados
        return sorted(list(set(r['materia'] for r in res.data)))

    def obtener_detalle_materia(self, materia: str) -> List[Dict[str, Any]]:
        """Obtiene todos los registros activos de una materia para armar el temario."""
        # Excluimos el historial 'estudiado' para ver solo el estado actual (p, d, repasar)
        return self.table.select("*").eq("materia", materia).neq("tipo", "estudiado").execute().data

db = DatabaseManager()