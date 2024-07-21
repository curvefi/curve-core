from dataclasses import dataclass

from eth_typing import Address


@dataclass
class CurveNetworkSettings:
    dao_ownership_contract: Address
    fee_receiver_address: Address
    metaregistry_address: Address | None = None
    base_pool_registry_address: Address | None = None
    address_provider: Address = "0x0000000022d53366457f9d5e68ec105046fc4383"
