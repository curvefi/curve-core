from enum import StrEnum
from pathlib import Path
from typing import Optional, List, Dict # Keeping Optional for explicit default typing

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# Define the base directory (two levels up from this file)
BASE_DIR: Path = Path(__file__).resolve().parent.parent


# --- Core Application Settings ---
class Settings(BaseSettings):
    """
    General application settings loaded from environment variables and an .env file.
    """
    
    # Use the Path operator / for cleaner path joining.
    # Assumes the environment file is named '.env' and located in the 'settings' subdirectory.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / "settings" / ".env",
        case_sensitive=True
    )

    DEBUG: bool = True
    DEV: bool = False

    # Required settings that must be defined in the environment
    WEB3_PROVIDER_URL: str
    DEPLOYER_EOA_PRIVATE_KEY: str # EOA stands for Externally Owned Account


# --- Configuration Schemas ---

class RollupType(StrEnum):
    """
    Defines the supported types of L2 rollup technologies.
    (Requires Python 3.11+ for StrEnum)
    """
    op_stack = "op_stack"
    arb_orbit = "arb_orbit"
    polygon_cdk = "polygon_cdk"
    zksync = "zksync"
    taiko = "taiko"
    not_rollup = "not_rollup"


class CurveDAOSettings(BaseModel):
    """
    Addresses for key DAO components on a specific chain.
    These fields are optional for chains that do not integrate with CurveDAO.
    """
    crv: str | None = None
    crvusd: str | None = None
    ownership_admin: str | None = None
    parameter_admin: str | None = None
    emergency_admin: str | None = None
    vault: str | None = None


class ReferenceTokenAddresses(BaseModel):
    """
    Standard token addresses used for cross-chain consistency or reference.
    These are typically required for proper indexing or price feeds.
    """
    usdc: str | None = None
    usdt: str | None = None
    weth: str | None = None


class ChainConfig(BaseSettings):
    """
    Comprehensive configuration model for a single blockchain network.
    This model supports loading values from environment variables or providing defaults.
    """
    
    # Ensures that enum values (like 'op_stack') are used as strings when loading/dumping.
    model_config = SettingsConfigDict(use_enum_values=True)

    # Core identification
    file_name: str
    file_path: str
    network_name: str
    is_testnet: bool
    chain_id: int
    layer: int

    # Technical specifications
    rollup_type: RollupType
    evm_version: str = "shanghai"
    wrapped_native_token: str

    # Explorer and Currency Details
    explorer_base_url: str
    logo_url: str
    native_currency_symbol: str
    native_currency_coingecko_id: str
    
    # Token and Infrastructure
    reference_token_addresses: ReferenceTokenAddresses
    public_rpc_url: str
    
    # Optional DeFi Integration Settings
    dao: CurveDAOSettings | None = None

    # Multicall Contracts (Default values for commonly used contracts)
    multicall2: str | None = None
    # Standard Multicall3 address (EIP-155 friendly address common across L2s/EVM chains)
    multicall3: str = "0xcA11bde05977b3631167028862bE2a173976CA11"
