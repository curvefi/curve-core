from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, YamlConfigSettingsSource

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(BASE_DIR, "settings", "env"))

    DEBUG: bool = False
    DEV: bool = False

    WEB3_PROVIDER_URL: str
    DEPLOYER_EOA_PRIVATE_KEY: str


settings = Settings()


class RollupType(StrEnum):
    op_stack = "op_stack"
    arb_orbit = "arb_orbit"
    polygon_cdk = "polygon_cdk"
    zksync = "zksync"
    taiko = "taiko"
    not_rollup = "_"


class CurveDAOSettings(BaseModel):
    crv: str | None = None
    crvusd: str | None = None
    ownership_admin: str | None = None
    parameter_admin: str | None = None
    emergency_admin: str | None = None
    vault: str | None = None


class ChainConfig(BaseSettings):
    model_config = SettingsConfigDict(use_enum_values=True)

    network_name: str
    chain_id: int
    layer: int
    rollup_type: RollupType
    wrapped_native_token: str
    dao: CurveDAOSettings | None = None
    explorer_base_url: str
    native_currency_symbol: str
    native_currency_coingecko_id: str
    platform_coingecko_id: str
    public_rpc_url: str


class CryptoPoolPresets(BaseModel):
    A: int = 20000000
    gamma: int = 1000000000000000
    mid_fee: int = 5000000
    out_fee: int = 45000000
    fee_gamma: int = 5000000000000000
    allowed_extra_profit: int = 10000000000
    adjustment_step: int = 5500000000000
    ma_exp_time: int = 866
    initial_price: int = 10**18


def get_chain_settings(chain: str):
    config_file = Path(BASE_DIR, "settings", "chains", f"{chain}.yaml")

    class YamlChainConfig(ChainConfig):
        model_config = SettingsConfigDict(yaml_file=config_file)

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
