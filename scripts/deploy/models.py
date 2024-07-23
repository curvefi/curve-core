from dataclasses import dataclass

from eth_typing import Address


@dataclass
class CurveDAONetworkSettings:
    dao_ownership_contract: Address
    fee_receiver_address: Address
    dao_parameter_contract: Address | None = None
    dao_emergency_contract: Address | None = None
    dao_vault_contract: Address | None = None
    crv_token_address: Address | None = None
    crvusd_token_address: Address | None = None
    metaregistry_address: Address | None = None
    address_provider_address: Address | None = None
