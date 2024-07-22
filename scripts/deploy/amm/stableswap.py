import logging
from pathlib import Path

import boa

from scripts.deploy.models import CurveNetworkSettings
from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR

logger = logging.getLogger(__name__)


def deploy_infra(chain: str, network_settings: CurveNetworkSettings):
    # owner = network_settings.dao_ownership_contract  # TODO: add grant access
    fee_receiver = network_settings.fee_receiver_address

    # --------------------- Deploy math, views, blueprints ---------------------

    # deploy non-blueprint contracts:
    math_contract = deploy_contract(chain, "stableswap", Path(BASE_DIR, "contracts", "amm", "stableswap", "math"))
    views_contract = deploy_contract(chain, "stableswap", Path(BASE_DIR, "contracts", "amm", "stableswap", "views"))

    # deploy blueprints:
    plain_blueprint = deploy_contract(
        chain, "stableswap", Path(BASE_DIR, "contracts", "amm", "stableswap", "implementation"), as_blueprint=True
    )
    meta_blueprint = deploy_contract(
        chain, "stableswap", Path(BASE_DIR, "contracts", "amm", "stableswap", "meta_implementation"), as_blueprint=True
    )

    # Factory:
    factory = deploy_contract(
        chain, "stableswap", Path(BASE_DIR, "contracts", "amm", "stableswap", "factory"), fee_receiver, boa.env.eoa
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
        factory.set_pool_implementations(0, plain_blueprint.address)
        logger.info(f"Set plain amm implementation at index 0 to: {plain_blueprint.address}")

    current_metapool_impl = factory.metapool_implementations(0)
    if not current_metapool_impl == meta_blueprint.address:
        logger.info(f"Current metapool impl at index 0: {current_metapool_impl}")
        factory.set_metapool_implementations(0, meta_blueprint.address)
        logger.info(f"Set meta amm implementation to: {meta_blueprint.address}")

    logger.info("Infra deployed!")
