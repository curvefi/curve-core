from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, YamlConfigSettingsSource

import settings.models as DataModels

BASE_DIR = Path(__file__).resolve().parent.parent
settings = DataModels.Settings()


def get_chain_settings(chain_config_file: str):
    config_file = Path(BASE_DIR, "settings", "chains", f"{chain_config_file}")

    class YamlChainConfig(DataModels.ChainConfig):
        model_config = SettingsConfigDict(yaml_file=config_file)
        file_path: str = chain_config_file
        file_name: str = config_file.stem

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            sources = super().settings_customise_sources(
                settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
            )
            return YamlConfigSettingsSource(settings_cls, yaml_file=config_file), *sources

    return YamlChainConfig()
