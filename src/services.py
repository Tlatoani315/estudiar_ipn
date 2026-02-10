# src/services.py
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, List
import random
from .database import db

class SpacedRepetitionService:

    @staticmethod
    def calcular_proxima_fecha(repasos_count: int, fecha_base: str) -> str:
        intervalos = [3, 7, 30] 
        idx = min(repasos_count - 1, 2)
        dias_a_sumar = intervalos[idx]
        fecha_obj = datetime.strptime(fecha_base, '%Y-%m-%d')
        return (fecha_obj + timedelta(days=dias_a_sumar)).strftime('%Y-%m-%d')

    @classmethod
    def procesar_estudio(cls, subtema_input: str) -> Tuple[str, Dict[str, Any]]:
        hoy = datetime.now().strftime('%Y-%m-%d')

        # 1. Buscar en Repasos (Activos)
        registro_repaso = db.buscar_repaso_especifico(subtema_input)
        if registro_repaso:
            cls._mover_a_historial(registro_repaso, hoy)
            db.eliminar_por_id(registro_repaso["id"])
            
            count = registro_repaso.get("repasos_count", 0)
            # Si no ha llegado a 4 repasos, se reprograma. Si llega a 4, ¿se domina o sigue?
            # Asumiremos que sigue en ciclo hasta que usuario use /dominado
            if count < 4:
                nueva_fecha = cls.calcular_proxima_fecha(count, hoy) # Usamos hoy como base real
                db.insertar_registro({
                    "tipo": "repasar",
                    "materia": registro_repaso["materia"],
                    "tema": registro_repaso["tema"],
                    "subtema": registro_repaso["subtema"],
                    "fecha": nueva_fecha,
                    "repasos_count": count + 1
                })
            return "Repaso completado", registro_repaso

        # 2. Buscar en Pendientes
        registro_pendiente = db.buscar_pendiente_especifico(subtema_input)
        if registro_pendiente:
            db.eliminar_por_id(registro_pendiente["id"])
            cls._mover_a_historial(registro_pendiente, hoy)
            
            mañana = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            db.insertar_registro({
                "tipo": "repasar",
                "materia": registro_pendiente["materia"],
                "tema": registro_pendiente["tema"],
                "subtema": registro_pendiente["subtema"],
                "fecha": mañana,
                "repasos_count": 1
            })
            return "Nuevo tema iniciado", registro_pendiente

        raise ValueError("No encontrado (¿Ya dominado o mal escrito?)")

    @staticmethod
    def _mover_a_historial(row: Dict[str, Any], fecha: str) -> None:
        # Solo guardamos el log de que se estudió hoy
        db.insertar_registro({
            "tipo": "estudiado",
            "materia": row["materia"],
            "tema": row["tema"],
            "subtema": row["subtema"],
            "fecha": fecha
        })

    @staticmethod
    def sugerir_nuevos_temas(materia: str, cantidad: int) -> List[Dict[str, Any]]:
        pendientes = db.obtener_pendientes_materia(materia)
        if not pendientes:
            return []
        
        # Selección aleatoria
        seleccion = random.sample(pendientes, min(len(pendientes), cantidad))
        return seleccion