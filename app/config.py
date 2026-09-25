import os
from typing import Dict, Type
from pydantic import Field, HttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


def _normalize_database_url(url: str) -> str:
    url = url.strip()
    for prefix in ('postgres://', 'postgresql+psycopg://', 'postgresql+psycopg2://'):
        if url.startswith(prefix):
            return 'postgresql://' + url[len(prefix):]
    return url


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    SECRET_KEY: str = Field(default='dev')
    RAILWAY_URL: str | None = Field(default=None, description="PostgreSQL connection string")
    DATABASE_URL: str | None = Field(default=None, description="Railway Postgres private connection string")
    DATABASE_PUBLIC_URL: str | None = Field(default=None, description="Railway Postgres public connection string")
    POSTGRES_URL: str | None = Field(default=None, description="Postgres connection string alias")

    @model_validator(mode='after')
    def normalize_database_aliases(self):
        url = self.RAILWAY_URL or self.DATABASE_URL or self.POSTGRES_URL or self.DATABASE_PUBLIC_URL
        if not url:
            raise ValueError('Set DATABASE_URL or RAILWAY_URL with the PostgreSQL connection string.')
        normalized = _normalize_database_url(url)
        self.RAILWAY_URL = normalized
        self.DATABASE_URL = normalized
        return self
    
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        # SQLAlchemy may default to psycopg v3; this app installs and uses psycopg2.
        return (self.RAILWAY_URL or self.DATABASE_URL or '').replace(
            'postgresql://', 'postgresql+psycopg2://', 1
        )

    SHEETS_TIMEOUT: int = 30
    EXTERNAL_API_BASE_URL: HttpUrl = Field(default='https://control-asistencia.up.railway.app')
    EXTERNAL_API_KEY: str | None = None
    EXTERNAL_API_TIMEOUT: int = 20
    INTEGRATION_API_KEY: str | None = None
    LOGISTICS_INTEGRATION_API_KEY: str | None = None
    REPARTO_COST_API_URL: str | None = None
    REPARTO_COST_API_KEY: str | None = None
    REPARTO_COST_EMPRESA_ID: str = '1'

    FRESCURA_API_BASE_URL: str | None = None
    FRESCURA_API_USER: str | None = None
    FRESCURA_API_PASSWORD: str | None = None
    FRESCURA_API_DEPOSITOS: str = '1,4'
    FRESCURA_API_DEPOSIT_MAP: str = '1:1,4:2'
    FRESCURA_API_TIMEOUT: int = 20
    FRESCURA_API_URL: str | None = None
    FRESCURA_API_TOKEN: str | None = None
    FRESCURA_API_PATH: str = '/api/frescura/articulos'
    
    DOTACION_ENTREGA_URL: str = Field(
        default='https://docs.google.com/spreadsheets/d/e/2PACX-1vTRrt57z-QDSRmDblvUV6AHs_Q1og0qgW0Ec-fp1L0QjLr8R_346nhHEkKsndqka-wQUdKSc2-3PizX/pub?output=csv&gid=1241670089;'
                'https://docs.google.com/spreadsheets/d/e/2PACX-1vTRrt57z-QDSRmDblvUV6AHs_Q1og0qgW0Ec-fp1L0QjLr8R_346nhHEkKsndqka-wQUdKSc2-3PizX/pub?output=csv&gid=249846040'
    )
    DOTACION_RECARGAS_URL: str = Field(
        default='https://docs.google.com/spreadsheets/d/e/2PACX-1vTRrt57z-QDSRmDblvUV6AHs_Q1og0qgW0Ec-fp1L0QjLr8R_346nhHEkKsndqka-wQUdKSc2-3PizX/pub?output=csv&gid=1883083406;'
                'https://docs.google.com/spreadsheets/d/e/2PACX-1vTRrt57z-QDSRmDblvUV6AHs_Q1og0qgW0Ec-fp1L0QjLr8R_346nhHEkKsndqka-wQUdKSc2-3PizX/pub?output=csv&gid=680588527'
    )
    
    DEBUG: bool = False

    @field_validator('DEBUG', mode='before')
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {'1', 'true', 't', 'yes', 'y', 'on'}:
                return True
            if normalized in {'0', 'false', 'f', 'no', 'n', 'off'}:
                return False
            return False
        return value

class DevelopmentSettings(AppSettings):
    DEBUG: bool = True

class ProductionSettings(AppSettings):
    DEBUG: bool = False

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
        # The direct psycopg2 pool needs a plain PostgreSQL DSN, without +driver.
        self.RAILWAY_URL = settings.RAILWAY_URL
        self.DATABASE_URL = settings.DATABASE_URL
        self.SQLALCHEMY_DATABASE_URI = str(settings.SQLALCHEMY_DATABASE_URI)
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False

# Mapping of instances for Flask
configs = {
    'development': Config(DevelopmentSettings()),
    'production':  Config(ProductionSettings()),
}
configs['default'] = configs['development']
