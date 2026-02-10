from supabase import create_client, Client
from typing import List, Dict, Any, Optional
from .config import settings

class DatabaseManager:
    """
    Manejador de la conexión con Supabase.
    Patrón Singleton implícito al instanciarse a nivel de módulo si se desea,
    o inyección de dependencias.
    """
    
    def __init__(self):
        self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.table = self.client.table("estudios")

    def existe_subtema(self, materia: str, tema: str, subtema: str) -> bool:
        """Verifica si la combinación Materia-Tema-Subtema existe."""
        res = self.table.select("id") \
            .eq("materia", materia) \
            .eq("tema", tema) \
            .eq("subtema", subtema) \
            .execute()
        return len(res.data) > 0

    def insertar_registro(self, data: Dict[str, Any]) -> None:
        """Inserta un registro genérico en la tabla."""
        self.table.insert(data).execute()

    def eliminar_por_id(self, registro_id: int) -> None:
        """Elimina un registro por su ID único."""
        self.table.delete().eq("id", registro_id).execute()

    def eliminar_por_campo(self, campo: str, valor: str) -> None:
        """Elimina registros donde campo == valor (ej. eliminar materia)."""
        self.table.delete().eq(campo, valor).execute()

    def obtener_pendientes(self) -> List[Dict[str, Any]]:
        """Obtiene todos los registros marcados como 'pendiente'."""
        return self.table.select("*").eq("tipo", "pendiente").execute().data

    def obtener_repasos_para_fecha(self, fecha_limite: str) -> List[Dict[str, Any]]:
        """Obtiene repasos programados para hoy o antes (atrasados)."""
        return self.table.select("*") \
            .eq("tipo", "repasar") \
            .lte("fecha", fecha_limite) \
            .execute().data

    def buscar_repaso_especifico(self, subtema: str, fecha_limite: str) -> Optional[Dict[str, Any]]:
        """Busca un repaso específico disponible para hoy."""
        res = self.table.select("*") \
            .eq("tipo", "repasar") \
            .eq("subtema", subtema) \
            .lte("fecha", fecha_limite) \
            .execute()
        return res.data[0] if res.data else None

    def buscar_pendiente_especifico(self, subtema: str) -> Optional[Dict[str, Any]]:
        """Busca un subtema específico en pendientes."""
        res = self.table.select("*") \
            .eq("tipo", "pendiente") \
            .eq("subtema", subtema) \
            .execute()
        return res.data[0] if res.data else None

    def obtener_historial(self) -> List[Dict[str, Any]]:
        """Obtiene todo el historial de lo estudiado."""
        return self.table.select("materia, tema, subtema, fecha") \
            .eq("tipo", "estudiado") \
            .execute().data

# Instancia para ser importada
db = DatabaseManager()