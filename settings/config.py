#!/usr/bin/env python3
"""
@fileoverview Dynamic configuration loader for chain-specific settings using Pydantic V2 and yaml_config.
This module defines a factory function to load YAML configuration files and ensures that 
YAML settings are loaded before environment variables, allowing environment variables to override.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, YamlConfigSettingsSource
from typing import Type, Tuple, Callable

# Assuming settings/models.py exists and contains DataModels.ChainConfig
import settings.models as DataModels 

# Resolve the base directory (two levels up from this file's location)
BASE_DIR: Path = Path(__file__).resolve().parent.parent

# --- FACTORY FUNCTION ---

def create_chain_config_model(config_file: Path) -> Type[DataModels.ChainConfig]:
    """
    Dynamically creates a Pydantic Settings class customized to load from a specific YAML file.

    This setup ensures that the YAML file is the *first* source loaded, allowing environment 
    variables and other default sources to override the values defined in the file.
    """

    class YamlChainConfig(DataModels.ChainConfig):
        # 1. Pydantic Settings Configuration
        model_config = SettingsConfigDict(
            yaml_file=config_file,
            extra="ignore",  # Ignore unknown fields in the YAML file for robustness
            case_sensitive=True,
            # Ensure proper path is handled if YAML contains relative paths
            env_file_encoding='utf-8' 
        )
        
        # 2. Additional File Metadata (Non-config fields, used for reference)
        file_path: str = config_file.as_posix()
        file_name: str = config_file.stem

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: Type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> Tuple[PydanticBaseSettingsSource, ...]:
            """
            Customizes the order of configuration sources to load the YAML file first.
            (YAML, then Init, Env, Dotenv, Secrets)
            """
            # Create the YAML source instance
            yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=config_file)
            
            # Retrieve default sources from the superclass
            default_sources = super().settings_customise_sources(
                settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
            )

            # Return YAML source first, followed by all default sources (excluding the initial ones 
            # returned by the super().settings_customise_sources call, as they are implicitly re-added
            # by Python's return syntax when using the *sources spread operator in the original)
            return (yaml_source, *default_sources)

    return YamlChainConfig


# --- PUBLIC INTERFACE ---

def get_chain_settings(chain_config_file: str) -> DataModels.ChainConfig:
    """
    Loads and validates chain configuration from a YAML file located in the settings/chains directory.
    
    Args:
        chain_config_file: The filename of the YAML config (e.g., 'ethereum.yaml').
        
    Returns:
        An instance of the validated ChainConfig model.
    """
    # Use Pythonic path joining syntax
    config_path: Path = BASE_DIR / "settings" / "chains" / chain_config_file

    if not config_path.exists():
        raise FileNotFoundError(f"Chain configuration file not found at: {config_path.as_posix()}")

    # Create the dynamic class and instantiate it to load the configuration
    YamlConfigClass = create_chain_config_model(config_path)
    
    return YamlConfigClass()


# --- OPTIONAL: Example of how to structure main execution (Removed the unnecessary global setting) ---
# Example: settings = get_chain_settings("my_chain.yaml")
