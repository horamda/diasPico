import os
from typing import Dict, Type
from pydantic import Field, PostgresDsn, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    SECRET_KEY: str = Field(default='dev')
    RAILWAY_URL: str = Field(..., description="PostgreSQL connection string")
    
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return self.RAILWAY_URL

    # MySQL Configuration
    MYSQL_HOST: str | None = None
    MYSQL_USER: str | None = None
    MYSQL_PASSWORD: str | None = None
    MYSQL_DB: str | None = None
    
    SHEETS_TIMEOUT: int = 30
    EXTERNAL_API_BASE_URL: HttpUrl = Field(default='https://control-asistencia.up.railway.app')
    EXTERNAL_API_KEY: str | None = None
    EXTERNAL_API_TIMEOUT: int = 20
    
    DOTACION_ENTREGA_URL: str = Field(
        default='https://docs.google.com/spreadsheets/d/e/2PACX-1vTRrt57z-QDSRmDblvUV6AHs_Q1og0qgW0Ec-fp1L0QjLr8R_346nhHEkKsndqka-wQUdKSc2-3PizX/pub?output=csv&gid=0;'
                'https://docs.google.com/spreadsheets/d/e/2PACX-1vTRrt57z-QDSRmDblvUV6AHs_Q1og0qgW0Ec-fp1L0QjLr8R_346nhHEkKsndqka-wQUdKSc2-3PizX/pub?output=csv&gid=249846040'
    )
    DOTACION_RECARGAS_URL: str = Field(
        default='https://docs.google.com/spreadsheets/d/e/2PACX-1vTRrt57z-QDSRmDblvUV6AHs_Q1og0qgW0Ec-fp1L0QjLr8R_346nhHEkKsndqka-wQUdKSc2-3PizX/pub?output=csv&gid=1883083406;'
                'https://docs.google.com/spreadsheets/d/e/2PACX-1vTRrt57z-QDSRmDblvUV6AHs_Q1og0qgW0Ec-fp1L0QjLr8R_346nhHEkKsndqka-wQUdKSc2-3PizX/pub?output=csv&gid=680588527'
    )
    
    DEBUG: bool = False

class DevelopmentSettings(AppSettings):
    DEBUG: bool = True

class ProductionSettings(AppSettings):
    DEBUG: bool = False

# Instantiate settings
settings = AppSettings()

def get_config(env: str = 'development') -> AppSettings:
    if env == 'production':
        return ProductionSettings()
    return DevelopmentSettings()

# Flask-compatible config mapping (can be used with app.config.from_object)
class Config:
    def __init__(self, settings: AppSettings):
        for field in settings.model_fields:
            value = getattr(settings, field)
            if isinstance(value, HttpUrl):
                value = str(value)
            setattr(self, field.upper(), value)
        
        # Add special SQLAlchemy keys
        self.SQLALCHEMY_DATABASE_URI = str(settings.RAILWAY_URL)
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False

# Mapping of instances for Flask
configs = {
    'development': Config(DevelopmentSettings()),
    'production':  Config(ProductionSettings()),
}
configs['default'] = configs['development']
