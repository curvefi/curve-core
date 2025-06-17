from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(BASE_DIR, "settings", "env"))

    DEBUG: bool = True
    DEV: bool = False

    WEB3_PROVIDER_URL: str
    DEPLOYER_EOA_PRIVATE_KEY: str


class RollupType(StrEnum):
    op_stack = "op_stack"
    arb_orbit = "arb_orbit"
    polygon_cdk = "polygon_cdk"
    zksync = "zksync"
    taiko = "taiko"
    not_rollup = "not_rollup"


class CurveDAOSettings(BaseModel):
    crv: str | None = None
    crvusd: str | None = None
    ownership_admin: str | None = None
    parameter_admin: str | None = None
    emergency_admin: str | None = None
    vault: str | None = None


class ReferenceTokenAddresses(BaseModel):
    usdc: str | None = None
    usdt: str | None = None
    weth: str | None = None


class ChainConfig(BaseSettings):
    model_config = SettingsConfigDict(use_enum_values=True)

    file_name: str
    file_path: str
    network_name: str
    is_testnet: bool
    chain_id: int
    layer: int
    rollup_type: RollupType
    evm_version: str = "shanghai"
    wrapped_native_token: str
    dao: CurveDAOSettings | None = None
    explorer_base_url: str
    logo_url: str
    native_currency_symbol: str
    native_currency_coingecko_id: str
    reference_token_addresses: ReferenceTokenAddresses
    public_rpc_url: str
    multicall2: str | None = None
    multicall3: str = "0xcA11bde05977b3631167028862bE2a173976CA11"
