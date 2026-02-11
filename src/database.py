# src/database.py
from supabase import create_client, Client
from typing import List, Dict, Any, Optional
from .config import settings

class DatabaseManager:
    def __init__(self):
        # No creamos el cliente aquí para evitar que se ate a un ciclo de eventos muerto
        pass

    def _get_table(self):
        """Genera una conexión fresca y segura para la operación actual."""
        client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return client.table("estudios")

    # --- Verificaciones ---
    def existe_subtema(self, materia: str, tema: str, subtema: str) -> bool:
        res = self._get_table().select("id").eq("materia", materia).eq("tema", tema).eq("subtema", subtema).execute()
        return len(res.data) > 0

    # --- Inserción / Actualización ---
    def insertar_registro(self, data: Dict[str, Any]) -> None:
        self._get_table().insert(data).execute()

    def marcar_como_dominado(self, subtema: str) -> bool:
        table = self._get_table()
        # Buscar si existe en repasos o pendientes
        res = table.select("*").eq("subtema", subtema).neq("tipo", "estudiado").execute()
        
        if not res.data:
            return False

        # Eliminamos registros viejos
        for row in res.data:
            table.delete().eq("id", row['id']).execute()

        # Insertamos como dominado
        from datetime import datetime
        hoy = datetime.now().strftime('%Y-%m-%d')
        table.insert({
            "tipo": "dominado",
            "materia": res.data[0]['materia'],
            "tema": res.data[0]['tema'],
            "subtema": subtema,
            "fecha": hoy
        }).execute()
        return True

    def eliminar_por_id(self, registro_id: int) -> None:
        self._get_table().delete().eq("id", registro_id).execute()

    def eliminar_por_campo(self, campo: str, valor: str) -> None:
        self._get_table().delete().eq(campo, valor).execute()

    # --- Consultas ---
    def obtener_pendientes_materia(self, materia: str) -> List[Dict[str, Any]]:
        return self._get_table().select("*").eq("tipo", "pendiente").eq("materia", materia).execute().data

    def obtener_pendientes(self) -> List[Dict[str, Any]]:
        return self._get_table().select("*").eq("tipo", "pendiente").execute().data

    def obtener_repasos_para_fecha(self, fecha_limite: str) -> List[Dict[str, Any]]:
        return self._get_table().select("*").eq("tipo", "repasar").lte("fecha", fecha_limite).execute().data

    def buscar_repaso_especifico(self, subtema: str) -> Optional[Dict[str, Any]]:
        res = self._get_table().select("*").eq("tipo", "repasar").eq("subtema", subtema).execute()
        return res.data[0] if res.data else None

    def buscar_pendiente_especifico(self, subtema: str) -> Optional[Dict[str, Any]]:
        res = self._get_table().select("*").eq("tipo", "pendiente").eq("subtema", subtema).execute()
        return res.data[0] if res.data else None

    # --- Métricas ---
    def obtener_todos_registros(self) -> List[Dict[str, Any]]:
        return self._get_table().select("materia, tema, subtema, tipo").execute().data

    def obtener_materias_unicas(self) -> List[str]:
        res = self._get_table().select("materia").execute()
        if not res.data:
            return []
        return sorted(list(set(r['materia'] for r in res.data)))

    def obtener_detalle_materia(self, materia: str) -> List[Dict[str, Any]]:
        return self._get_table().select("*").eq("materia", materia).execute().dat

    def buscar_repaso_especifico(self, subtema: str) -> Optional[Dict[str, Any]]:
        # Usamos ilike para que no importe si escribes "sistemas" o "Sistemas"
        res = self._get_table().select("*").eq("tipo", "repasar").ilike("subtema", subtema).execute()
        return res.data[0] if res.data else None

    def buscar_pendiente_especifico(self, subtema: str) -> Optional[Dict[str, Any]]:
        res = self._get_table().select("*").eq("tipo", "pendiente").ilike("subtema", subtema).execute()
        return res.data[0] if res.data else None

    def obtener_cronograma_completo(self) -> List[Dict[str, Any]]:
        """Obtiene tanto lo estudiado (pasado) como lo programado (futuro)"""
        # Traemos registros de tipo estudiado y repasar
        res = self._get_table().select("*").in_("tipo", ["estudiado", "repasar"]).order("fecha").execute()
        return res.data

# Instancia global (ahora segura porque es "stateless")
db = DatabaseManager()