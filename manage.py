import boa
import click
from eth_account import Account

# Import the deployer and test command groups from their respective modules
from scripts.deploy import deploy_commands
from scripts.tests import test_commands
from settings.config import settings


@click.group("commands")
def commands():
    """
    Main entry point for the project CLI commands.
    This group acts as a container for deployment and testing commands.
    """
    pass


if __name__ == "__main__":
    # --- Boa Environment Setup ---
    # This block configures the Web3 environment based on the DEBUG setting.

    if settings.DEBUG:
        # If DEBUG is True, use Boa's forking mode.
        # This creates an isolated local environment that mirrors the state 
        # of the specified live network at the "latest" block, allowing for 
        # fast, safe, and repeatable testing without spending real gas.
        # 
        print(f"Setting up forked environment from: {settings.WEB3_PROVIDER_URL}")
        boa.fork(settings.WEB3_PROVIDER_URL, block_identifier="latest")
    else:
        # If DEBUG is False, connect directly to the live network.
        # This is used for actual deployments or state modifications.
        print(f"Connecting to live network: {settings.WEB3_PROVIDER_URL}")
        boa.set_network_env(settings.WEB3_PROVIDER_URL)
        
        # Load the deployer account using the private key for signing transactions.
        # This step is critical for deployment commands.
        try:
            deployer_account = Account.from_key(settings.DEPLOYER_EOA_PRIVATE_KEY)
            boa.env.add_account(deployer_account)
            print(f"Deployer account added: {deployer_account.address}")
        except ValueError:
             print("Error: DEPLOYER_EOA_PRIVATE_KEY is invalid or missing.")
             exit(1)


    # --- CLI Command Registration and Execution ---

    # Add the deployment commands group to the main CLI
    commands.add_command(deploy_commands)
    
    # Add the testing commands group to the main CLI
    commands.add_command(test_commands)
    
    # Run the Click CLI
    commands()
