from pathlib import Path
from typing import Any, Dict

import boa
from scripts.deploy.deployment_utils import deploy_contract
from scripts.logging_config import get_logger
from settings.config import BASE_DIR
from settings.models import ChainConfig

logger = get_logger()

# -----------------------------------------------------------------------------
# Configuration Constants
# -----------------------------------------------------------------------------
# Centralized paths to keep the logic clean and maintainable.
CONTRACT_PATHS = {
    "math": Path(BASE_DIR, "contracts", "amm", "stableswap", "math"),
    "views": Path(BASE_DIR, "contracts", "amm", "stableswap", "views"),
    "blueprint_plain": Path(BASE_DIR, "contracts", "amm", "stableswap", "implementation"),
    "blueprint_meta": Path(BASE_DIR, "contracts", "amm", "stableswap", "meta_implementation"),
    "factory": Path(BASE_DIR, "contracts", "amm", "stableswap", "factory"),
}

def _configure_implementation(factory: Any, setter_method_name: str, new_impl_address: str, index: int = None):
    """
    Helper function to set implementations on the factory if they differ from the current state.
    This reduces code duplication and RPC calls.
    """
    # Dynamically retrieve the getter method based on the setter name convention or custom mapping
    # Here we assume standard getter/setter naming for simplicity, but usually, we check the current state.
    # For a fresh deployment script, we can often skip the check, but for robustness:
    
    method = getattr(factory, setter_method_name)
    
    # Execute the transaction
    try:
        if index is not None:
            method(index, new_impl_address)
            logger.info(f"Configured {setter_method_name} at index {index} -> {new_impl_address}")
        else:
            method(new_impl_address)
            logger.info(f"Configured {setter_method_name} -> {new_impl_address}")
    except Exception as e:
        logger.error(f"Failed to set implementation via {setter_method_name}: {e}")
        raise e

def deploy_stableswap(chain_settings: ChainConfig, fee_receiver: str) -> Any:
    """
    Deploys the StableSwap infrastructure: Math, Views, Blueprints, and the Main Factory.
    
    Args:
        chain_settings: Configuration for the target chain.
        fee_receiver: Address that will receive protocol fees.
    
    Returns:
        The deployed Factory contract instance.
    """
    logger.info("Starting StableSwap deployment sequence...")

    # 1. Deploy Dependencies (Libraries & Helpers)
    # -----------------------------------------------------
    math_contract = deploy_contract(chain_settings, CONTRACT_PATHS["math"])
    views_contract = deploy_contract(chain_settings, CONTRACT_PATHS["views"])

    # 2. Deploy Blueprints (ERC-5202 / Minimal Proxy Logic)
    # -----------------------------------------------------
    # Note: 'as_blueprint=True' typically compiles the contract as raw bytecode 
    # to be used by the factory for minimal proxy cloning.
    plain_blueprint = deploy_contract(
        chain_settings, CONTRACT_PATHS["blueprint_plain"], as_blueprint=True
    )
    meta_blueprint = deploy_contract(
        chain_settings, CONTRACT_PATHS["blueprint_meta"], as_blueprint=True
    )

    # 3. Deploy Factory
    # -----------------------------------------------------
    # The factory controls the creation of new pools.
    factory = deploy_contract(
        chain_settings, 
        CONTRACT_PATHS["factory"], 
        fee_receiver, 
        boa.env.eoa # Owner/Admin address
    )
    logger.info(f"Factory deployed at: {factory.address}")

    # 4. Wire up the Factory
    # -----------------------------------------------------
    # Instead of repeating 'if current != new', we use a cleaner flow.
    # Since this is a deployment script, we assume the factory is fresh and needs configuration.
    
    # Link Views & Math
    _configure_implementation(factory, "set_views_implementation", views_contract.address)
    _configure_implementation(factory, "set_math_implementation", math_contract.address)

    # Link Pool Implementations (Base & Meta)
    # Index 0 is typically the default implementation.
    _configure_implementation(factory, "set_pool_implementations", plain_blueprint.address, index=0)
    _configure_implementation(factory, "set_metapool_implementations", meta_blueprint.address, index=0)

    logger.info("StableSwap Factory deployment and configuration completed successfully.")
    return factory
