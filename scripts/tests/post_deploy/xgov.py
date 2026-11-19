from scripts.deploy.constants import STORAGE_PROOF_ROLLUPS, get_relayer_type
from scripts.deploy.models import Contract, DeploymentConfig
from scripts.tests.post_deploy.utils import check_contracts, check_if_contract_deployed, get_contract


def test_xgov_deployment(deployment: DeploymentConfig):
    current_deployment = deployment.contracts.governance
    if current_deployment is None:
        return

    rollup_type = deployment.config.rollup_type
    verifier: Contract | None = current_deployment.verifier

    # deployments made before the switch to storage proofs use native bridge relayers
    uses_storage_proofs = rollup_type in STORAGE_PROOF_ROLLUPS and verifier is not None

    current_deployment = current_deployment.model_dump(exclude={"blockhash_oracle", "verifier"})
    relayer_type = get_relayer_type(rollup_type) if uses_storage_proofs else rollup_type
    current_deployment["relayer"] = current_deployment["relayer"][relayer_type]
    if uses_storage_proofs:
        current_deployment["blockhash_oracle"] = deployment.contracts.governance.blockhash_oracle[
            rollup_type
        ].model_dump()

    contracts = {
        k: {**v, "contract": get_contract(v["contract_path"], v["address"])} for k, v in current_deployment.items()
    }
    check_contracts(contracts)

    relayer = contracts["relayer"]["contract"]

    assert relayer.OWNERSHIP_AGENT() == deployment.config.dao.ownership_admin
    assert relayer.PARAMETER_AGENT() == deployment.config.dao.parameter_admin
    assert relayer.EMERGENCY_AGENT() == deployment.config.dao.emergency_admin

    if uses_storage_proofs:
        # Solidity contract without `version()`, checked separately
        assert check_if_contract_deployed(verifier.address) is True
        verifier_contract = verifier.get_contract()

        # messages are accepted only from Verifier, which trusts the native Block Hash Oracle
        assert relayer.messenger() == verifier.address
        assert verifier_contract.RELAYER() == relayer.address
        assert verifier_contract.BLOCK_HASH_ORACLE() == contracts["blockhash_oracle"]["contract"].address
