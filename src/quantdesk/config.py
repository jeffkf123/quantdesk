from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path

class Settings(BaseSettings):
    data_dir: Path = Field(default=Path("./data"))
    parquet_dir: Path = Field(default=Path("./data/parquet"))
    log_level: str = Field(default="INFO")

    model_config = {"env_prefix": "QD_", "env_file": ".env", "extra": "ignore"}

settings = Settings()  # singleton-style import
