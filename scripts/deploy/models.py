from enum import StrEnum, auto
from pathlib import Path

import boa
from pydantic import BaseModel
from pydantic import ConfigDict as BaseModelConfigDict

from settings.config import BASE_DIR, ChainConfig

#  <-------------------------- Chain Config -------------------------->


class DaoSettings(BaseModel):
    crv: str | None = None
    crvusd: str | None = None
    emergency_admin: str | None = None
    ownership_admin: str | None = None
    parameter_admin: str | None = None
    vault: str | None = None


#  <-------------------------- Contracts -------------------------->


class CompilerSettings(BaseModel):
    compiler_version: str
    evm_version: str | None
    optimisation_level: str


class DeploymentType(StrEnum):
    normal = auto()
    blueprint = auto()


class Contract(BaseModel):
    model_config = BaseModelConfigDict(use_enum_values=True)

    address: str
    compiler_settings: CompilerSettings
    constructor_args_encoded: str | None
    contract_github_url: str
    contract_path: str
    contract_version: str
    deployment_timestamp: int
    deployment_type: DeploymentType

    def get_contract(self):
        contract_path = BASE_DIR / Path(self.contract_path.lstrip("/"))
        return boa.load_partial(contract_path).at(self.address)


#  <-------------------------- Deployments -------------------------->


class SingleAmmDeployment(BaseModel):
    factory: Contract | None = None
    implementation: Contract | None = None
    math: Contract | None = None
    views: Contract | None = None


class StableswapSingleAmmDeployment(SingleAmmDeployment):
    meta_implementation: Contract | None = None


class AmmDeployment(BaseModel):
    stableswap: StableswapSingleAmmDeployment | None = None
    tricryptoswap: SingleAmmDeployment | None = None
    twocryptoswap: SingleAmmDeployment | None = None


#  <----------------------------------------------------------------->


class GaugeFactoryDeployment(BaseModel):
    factory: Contract | None = None
    implementation: Contract | None = None


class GaugeDeployment(BaseModel):
    child_gauge: GaugeFactoryDeployment


#  <----------------------------------------------------------------->


class GovernanceDeployment(BaseModel):
    agent: Contract | None = None
    relayer: dict[str, Contract] | None = None  # str should be RollupType
    vault: Contract | None = None


#  <----------------------------------------------------------------->


class HelpersDeployment(BaseModel):
    deposit_and_stake_zap: Contract | None = None
    rate_provider: Contract | None = None
    router: Contract | None = None
    stable_swap_meta_zap: Contract | None = None


#  <----------------------------------------------------------------->


class MetaregistryHandlers(BaseModel):
    stableswap: Contract | None = None
    tricryptoswap: Contract | None = None
    twocryptoswap: Contract | None = None


class MetaregistyContract(Contract):
    registry_handlers: MetaregistryHandlers | None = None


class RegistriesDeployment(BaseModel):
    address_provider: Contract | None = None
    metaregistry: MetaregistyContract | None = None


#  <----------------------------------------------------------------->


class ContractsDeployment(BaseModel):
    amm: AmmDeployment | None = None
    gauge: GaugeDeployment | None = None
    governance: GovernanceDeployment | None = None
    helpers: HelpersDeployment | None = None
    registries: RegistriesDeployment | None = None


class DeploymentConfig(BaseModel):
    config: ChainConfig
    contracts: ContractsDeployment | None = None
