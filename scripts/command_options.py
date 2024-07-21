import os

import click

chain = click.option("--chain", type=click.STRING, prompt=True, default=lambda: os.environ.get("CHAIN", None))
chain_id = click.option("--chain_id", type=click.INT, prompt=True, default=lambda: os.environ.get("CHAIN_ID", None))
weth = click.option("--weth", type=click.STRING, prompt=True, default=lambda: os.environ.get("WETH", None))

owner = click.option("--owner", type=click.STRING, prompt=True)
fee_receiver = click.option("--fee_receiver", type=click.STRING, prompt=True)
