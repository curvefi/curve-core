from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(BASE_DIR, "settings", "env"))

    DEBUG: bool = True
    DEV: bool = False

    # Empty defaults so read-only commands (`manage.py status`) work on a fresh clone with
    # no settings/env. manage.py checks these are populated before any command that needs
    # to reach a chain, so a deploy still fails loudly rather than connecting to "".
    WEB3_PROVIDER_URL: str = ""
    DEPLOYER_EOA_PRIVATE_KEY: str = ""


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
    # Present in sonic.yaml and taiko.yaml. Undeclared until now, and pydantic's
    # extra='ignore' plus the model_dump() round-trip in update_deployment_config() meant
    # any further deploy step against those chains deleted it - from the file and from what
    # curve-api-core serves.
    scrvusd: str | None = None
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
    native_token: str | None = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
    wrapped_native_token: str
    wrapper: str | None = None
    dao: CurveDAOSettings | None = None
    explorer_base_url: str
    logo_url: str
    native_currency_symbol: str
    native_currency_coingecko_id: str
    reference_token_addresses: ReferenceTokenAddresses
    public_rpc_url: str
    multicall2: str | None = None
    multicall3: str = "0xcA11bde05977b3631167028862bE2a173976CA11"

    @field_validator("wrapper", mode="after")
    def default_wrapper(cls, v, info):
        if v is None:
            return info.data["wrapped_native_token"]
        return v
