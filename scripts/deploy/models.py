from dataclasses import dataclass

from eth_typing import Address


@dataclass
class CurveDAONetworkSettings:
    dao_ownership_contract: Address
    dao_parameter_contract: Address
    dao_emergency_contract: Address
    dao_vault_contract: Address
    crv_token_address: Address
    crvusd_token_address: Address
    fee_receiver_address: Address
    metaregistry_address: Address
    address_provider: Address
