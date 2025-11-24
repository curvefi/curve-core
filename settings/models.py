import os
from enum import StrEnum
from pathlib import Path
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the base directory of the project. 
# This is typically the root folder two levels above the current file.
# Note: For production use, consider loading settings based on project root 
# determined by packaging tools rather than __file__.
BASE_DIR = Path(__file__).resolve().parent.parent


## --- Application-Wide Settings ---

class Settings(BaseSettings):
    """
    Core application settings loaded from environment variables or a specified .env file.
    Includes sensitive keys and debug flags.
    """
    # Configure Pydantic to look for settings in a specific file relative to BASE_DIR
    model_config = SettingsConfigDict(env_file=Path(BASE_DIR, "settings", "env"))

    # Debugging and environment flags
    DEBUG: bool = Field(default=True, description="Enable debug mode.")
    DEV: bool = Field(default=False, description="Development environment flag.")

    # Critical Web3 connection settings (required and loaded from ENV)
    WEB3_PROVIDER_URL: str = Field(description="URL for the RPC node provider.")
    DEPLOYER_EOA_PRIVATE_KEY: str = Field(description="Private key for the EOA used for deployments.")


## --- Chain Configuration Enums and Models ---

class RollupType(StrEnum):
    """Defines the type of Layer 2 Rollup technology."""
    op_stack = "op_stack"
    arb_orbit = "arb_orbit"
    polygon_cdk = "polygon_cdk"
    zksync = "zksync"
    taiko = "taiko"
    not_rollup = "not_rollup"


class CurveDAOSettings(BaseModel):
    """Addresses for key Curve DAO components on a specific chain."""
    crv: Optional[str] = Field(default=None, description="CRV token address.")
    crvusd: Optional[str] = Field(default=None, description="crvUSD stablecoin address.")
    ownership_admin: Optional[str] = Field(default=None, description="Address of the ownership administrator.")
    parameter_admin: Optional[str] = Field(default=None, description="Address of the parameter administrator.")
    emergency_admin: Optional[str] = Field(default=None, description="Address of the emergency administrator.")
    vault: Optional[str] = Field(default=None, description="Vault address.")


class ReferenceTokenAddresses(BaseModel):
    """Addresses for commonly used reference tokens."""
    usdc: Optional[str] = Field(default=None, description="USDC token address.")
    usdt: Optional[str] = Field(default=None, description="USDT token address.")
    weth: Optional[str] = Field(default=None, description="Wrapped Ether token address.")


class ChainConfig(BaseSettings):
    """
    Configuration for a specific EVM blockchain (Layer 1 or Layer 2).
    This model would typically be loaded from a configuration file (e.g., JSON/YAML)
    per chain, thanks to the BaseSettings structure.
    """
    # Use enum values (strings) when loading from configuration files
    model_config = SettingsConfigDict(use_enum_values=True)

    file_name: str = Field(description="Original configuration file name.")
    file_path: str = Field(description="Path to the configuration file.")
    network_name: str = Field(description="Human-readable network name.")
    is_testnet: bool = Field(description="True if the chain is a testnet.")
    chain_id: int = Field(description="The chain ID (EIP-155).")
    layer: int = Field(description="The layer number (1 for L1, 2 for L2).")
    rollup_type: RollupType = Field(description="The underlying L2 rollup technology.")
    evm_version: str = Field(default="shanghai", description="The minimum EVM hardfork version.")
    wrapped_native_token: str = Field(description="WETH/WBNB/etc. token address.")
    dao: Optional[CurveDAOSettings] = Field(default=None, description="Optional Curve DAO related addresses.")
    explorer_base_url: str = Field(description="Base URL for the block explorer.")
    logo_url: str = Field(description="URL for the network's logo.")
    native_currency_symbol: str = Field(description="Symbol for the native currency (e.g., ETH, BNB).")
    native_currency_coingecko_id: str = Field(description="CoinGecko ID for the native currency.")
    reference_token_addresses: ReferenceTokenAddresses = Field(description="Commonly traded token addresses.")
    public_rpc_url: str = Field(description="Public RPC endpoint URL.")
    
    # Multicall addresses (Multicall3 is generally standard)
    multicall2: Optional[str] = Field(default=None, description="Multicall2 contract address (optional).")
    multicall3: str = Field(
        default="0xcA11bde05977b3631167028862bE2a173976CA11", 
        description="Standard Multicall3 contract address (EIP-2544). This is commonly the same across EVM chains."
    )
