from dataclasses import dataclass

from eth_typing import Address


@dataclass
class CurveNetworkSettings:
    dao_ownership_contract: Address
    fee_receiver_address: Address
    metaregistry_address: Address
    address_provider: Address
