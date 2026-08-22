from pathlib import Path
from typing import Type

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# Assuming settings.models is available and contains ChainConfig class.
import settings.models as DataModels

# Define the base directory of the project, typically two levels up from this file.
BASE_DIR = Path(__file__).resolve().parent.parent


def get_chain_settings(chain_config_file: str) -> DataModels.ChainConfig:
    """
    Dynamically loads chain-specific configuration from a YAML file.

    This method uses Pydantic's custom settings sources to ensure the YAML file
    is loaded and prioritized before environment variables or other sources.

    :param chain_config_file: The name of the chain configuration YAML file (e.g., 'ethereum.yaml').
    :return: An instance of ChainConfig loaded with data from the specified file.
    :raises FileNotFoundError: If the specified configuration file does not exist.
    """
    # 1. Construct the absolute path to the configuration file.
    config_path = BASE_DIR / "settings" / "chains" / chain_config_file

    # Check if the file exists to provide an early and clearer error message.
    if not config_path.exists():
        raise FileNotFoundError(f"Chain configuration file not found at: {config_path}")

    # 2. Define a specialized Pydantic BaseSettings class dynamically.
    # This nested class inherits the structure (fields) but customizes the source (where data comes from).
    class YamlChainConfig(DataModels.ChainConfig):
        # Optional: Add metadata fields to the instance, derived from the file path.
        # These are not Pydantic fields, just class attributes for context.
        file_path: str = str(config_path)
        file_name: str = config_path.stem

        # Pydantic configuration dictionary.
        model_config = SettingsConfigDict(
            # Ignore extra fields found in the YAML for robustness.
            extra='ignore'
        )

        @classmethod
        def settings_customise_sources(
            cls: Type[BaseSettings],
            settings_cls: Type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            """
            Overrides the default source loading order.

            It places the YAML configuration source first, guaranteeing that values
            from the file are loaded and prioritized over all subsequent sources
            (like environment variables).
            """
            # Create the YAML source instance.
            yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=config_path)

            # Retrieve default sources from the base class.
            default_sources = super().settings_customise_sources(
                settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
            )

            # Prepend the YAML source to the tuple of default sources.
            return (yaml_source, *default_sources)

    # 3. Instantiate the dynamically configured class. Pydantic automatically
    # loads the data from the customized sources upon instantiation.
    return YamlChainConfig()
