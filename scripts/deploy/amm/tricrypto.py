import logging
from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR, ChainConfig

logger = logging.getLogger(__name__)


def deploy_tricrypto(chain_settings: ChainConfig, fee_receiver):

    # --------------------- Deploy math, views, blueprints ---------------------

    # deploy non-blueprint contracts:
    math_contract = deploy_contract(chain_settings, Path(BASE_DIR, "contracts", "amm", "tricryptoswap", "math"))
    views_contract = deploy_contract(chain_settings, Path(BASE_DIR, "contracts", "amm", "tricryptoswap", "views"))

    # deploy blueprints:
    plain_blueprint = deploy_contract(
        chain_settings, Path(BASE_DIR, "contracts", "amm", "tricryptoswap", "implementation"), as_blueprint=True
    )

    # Factory:
    factory = deploy_contract(
        chain_settings, Path(BASE_DIR, "contracts", "amm", "tricryptoswap", "factory"), fee_receiver
    )

    # Set up AMM implementations:÷
    current_views_impl = factory.views_implementation()
    if not current_views_impl == views_contract.address:
        logger.info(f"Current views implementation: {current_views_impl}")
        factory.set_views_implementation(views_contract.address)
        logger.info(f"Set views implementation to: {views_contract.address}")

    current_math_impl = factory.math_implementation()
    if not current_math_impl == math_contract.address:
        logger.info(f"Current math implementation: {current_math_impl}")
        factory.set_math_implementation(math_contract.address)
        logger.info(f"Set math implementation to: {math_contract.address}")

    current_pool_impl = factory.pool_implementations(0)
    if not current_pool_impl == plain_blueprint.address:
        logger.info(f"Current 'plain' pool impl at index 0: {current_pool_impl}")
        factory.set_pool_implementation(plain_blueprint.address, 0)
        logger.info(f"Set plain amm implementation at index 0 to: {plain_blueprint.address}")

    logger.info("TricryptoSwap Factory deployed.")
    return factory
