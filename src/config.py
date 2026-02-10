import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Carga variables de entorno desde el archivo .env si existe
load_dotenv()

@dataclass(frozen=True)
class Config:
    """
    Configuración global inmutable de la aplicación.
    Valida la existencia de las variables críticas al iniciar.
    """
    TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN")
    SUPABASE_URL: str = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY")
    PORT: int = int(os.environ.get("PORT", 10000))

    def validate(self) -> None:
        """Verifica que todas las variables críticas estén definidas."""
        missing = [key for key, val in self.__dict__.items() if val is None]
        if missing:
            raise ValueError(f"Faltan variables de entorno críticas: {', '.join(missing)}")

# Instancia global de configuración
settings = Config()
settings.validate()