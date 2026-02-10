from datetime import datetime, timedelta
from typing import Tuple, Dict, Any
from .database import db

class SpacedRepetitionService:
    """
    Servicio que encapsula la lógica de negocio del sistema de estudio
    y el algoritmo de repetición espaciada (SR).
    """

    @staticmethod
    def _calcular_proxima_fecha(repasos_count: int, fecha_base: str) -> str:
        """
        Algoritmo interno de repetición espaciada.
        Intervalos: 1er (+1 día), 2do (+3), 3ro (+7), 4to (+30).
        """
        intervalos = [3, 7, 30] # Días a sumar según el conteo (índice count-1)
        # Nota: El primer repaso (count=0 -> 1) se maneja manualmente al crear el registro
        
        idx = min(repasos_count - 1, 2)
        dias_a_sumar = intervalos[idx]
        
        fecha_obj = datetime.strptime(fecha_base, '%Y-%m-%d')
        nueva_fecha = (fecha_obj + timedelta(days=dias_a_sumar)).strftime('%Y-%m-%d')
        return nueva_fecha

    @classmethod
    def procesar_estudio(cls, subtema_input: str) -> Tuple[str, Dict[str, Any]]:
        """
        Orquesta el flujo de marcar un tema como estudiado.
        Determina si es un repaso o un tema nuevo y actualiza la BD.
        
        Returns:
            Tuple: (Mensaje de estado, Fila del registro procesado)
        """
        hoy = datetime.now().strftime('%Y-%m-%d')

        # 1. Intentar procesar como REPASO
        registro_repaso = db.buscar_repaso_especifico(subtema_input, hoy)
        
        if registro_repaso:
            cls._mover_a_historial(registro_repaso, hoy)
            db.eliminar_por_id(registro_repaso["id"])
            
            # Programar siguiente repaso si no se ha graduado
            count = registro_repaso.get("repasos_count", 0)
            if count < 4:
                nueva_fecha = cls._calcular_proxima_fecha(count, registro_repaso["fecha"])
                db.insertar_registro({
                    "tipo": "repasar",
                    "materia": registro_repaso["materia"],
                    "tema": registro_repaso["tema"],
                    "subtema": registro_repaso["subtema"],
                    "fecha": nueva_fecha,
                    "repasos_count": count + 1
                })
            return "Repaso completado", registro_repaso

        # 2. Intentar procesar como PENDIENTE
        registro_pendiente = db.buscar_pendiente_especifico(subtema_input)
        
        if registro_pendiente:
            db.eliminar_por_id(registro_pendiente["id"])
            cls._mover_a_historial(registro_pendiente, hoy)
            
            # Crear primer repaso para mañana
            mañana = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            db.insertar_registro({
                "tipo": "repasar",
                "materia": registro_pendiente["materia"],
                "tema": registro_pendiente["tema"],
                "subtema": registro_pendiente["subtema"],
                "fecha": mañana,
                "repasos_count": 1
            })
            return "Nuevo tema estudiado", registro_pendiente

        raise ValueError("No encontrado en pendientes ni en repasos para hoy")

    @staticmethod
    def _mover_a_historial(row: Dict[str, Any], fecha: str) -> None:
        """Helper para registrar en el log de estudiados."""
        db.insertar_registro({
            "tipo": "estudiado",
            "materia": row["materia"],
            "tema": row["tema"],
            "subtema": row["subtema"],
            "fecha": fecha
        })