import click
from typing import TYPE_CHECKING # For circular imports/runtime checks

from scripts.logging_config import get_logger
from scripts.tests.post_deploy import test_post_deploy
from scripts.tests.pre_deployment import test_pre_deploy
from settings.config import get_chain_settings

# Conditional import for type checking only (if Settings is in settings.config)
if TYPE_CHECKING:
    from settings.config import Settings

logger = get_logger()

# --- Main Command Group ---

@click.group(name="test")
def test_commands():
    """Commands related to deployment testing (pre and post)."""
    pass

# --- Subcommand 1: Pre-Deployment Tests ---

@test_commands.command("pre_deploy", short_help="Run pre-deploy tests for a specific chain configuration.")
@click.argument("chain_config_file", type=click.STRING)
def run_test_pre_deploy(chain_config_file: str):
    """
    Loads chain settings and executes preliminary tests before deployment.
    """
    # Explicitly load and type the settings object
    settings: 'Settings' = get_chain_settings(chain_config_file)
    
    logger.info(f"Starting pre-deploy tests for Chain ID: {settings.chain_id}")
    
    # Pass only the necessary Chain ID to the test runner
    test_pre_deploy(settings.chain_id)
    
    logger.info("Pre-deploy tests completed successfully.")


# --- Subcommand 2: Post-Deployment Tests ---

@test_commands.command("post_deploy", short_help="Run post-deploy tests against a deployed contract.")
@click.argument("chain_config_file", type=click.STRING)
def run_test_post_deploy(chain_config_file: str):
    """
    Executes integration or validation tests after contract deployment.
    """
    # NOTE: Assuming test_post_deploy loads its own settings internally 
    # as the raw file path is passed directly (consistent with original code).
    logger.info(f"Starting post-deploy tests using config file: {chain_config_file}")
    
    test_post_deploy(chain_config_file)
    
    logger.info("Post-deploy tests completed successfully.")
