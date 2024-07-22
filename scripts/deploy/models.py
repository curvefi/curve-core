from dataclasses import dataclass

from eth_typing import Address


@dataclass
class CurveNetworkSettings:
    dao_ownership_contract: Address
    fee_receiver_address: Address
    metaregistry_address: Address | None = None  # TODO: add from deployments
    address_provider: Address = "0x0000000022D53366457F9d5E68Ec105046FC4383"  # TODO: add from deployments
