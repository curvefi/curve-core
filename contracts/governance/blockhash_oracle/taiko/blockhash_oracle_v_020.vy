# pragma version 0.4.3
"""
@title Taiko Block Hash oracle
@author Curve Finance
@license MIT
@notice Ethereum block hashes and state roots taken from Taiko's native L1 checkpoints.
@dev Supersedes 0.1.0 which used `SignalService.getSyncedChainData`, removed in Shasta upgrade.
@custom:version 0.2.0
@custom:kill Stateless and ownerless, can not be disabled. Consumers should be migrated to another
    oracle if Taiko changes or shuts down its checkpoints feed.
@custom:security Trusts Taiko's SignalService (upgradeable by Taiko) and its checkpoints syncer:
    a malicious or broken feed lets forge any Ethereum state. Checkpoints are saved only for
    some of Ethereum blocks, unknown blocks revert. Contact: security@curve.fi
"""

from contracts.governance.blockhash_oracle import IBlockHashOracle

implements: IBlockHashOracle


interface ISignalService:
    def getCheckpoint(_blockNumber: uint48) -> Checkpoint: view


struct Checkpoint:
    blockNumber: uint48
    blockHash: bytes32
    stateRoot: bytes32


version: public(constant(String[8])) = "0.2.0"

# Taiko Alethia predeploy: 0x{chain id}0...05
SIGNAL_SERVICE: public(constant(ISignalService)) = ISignalService(
    0x1670000000000000000000000000000000000005
)

MAX_LOOKUP: constant(uint256) = 3600 // 12  # Ethereum blocks in an hour


@internal
@view
def _checkpoint(_number: uint256) -> Checkpoint:
    # Reverts if there is no checkpoint for the block
    checkpoint: Checkpoint = staticcall SIGNAL_SERVICE.getCheckpoint(convert(_number, uint48))
    assert convert(checkpoint.blockNumber, uint256) == _number, "Bad checkpoint"
    return checkpoint


@external
@view
def get_block_hash(_number: uint256) -> bytes32:
    """
    @notice Query the block hash of a block.
    @dev Reverts for unknown block numbers.
    @param _number Number of the block to look for.
    @return Hash of Ethereum block.
    """
    block_hash: bytes32 = self._checkpoint(_number).blockHash
    assert block_hash != empty(bytes32), "Empty block hash"

    return block_hash


@external
@view
def get_state_root(_number: uint256) -> bytes32:
    """
    @notice Query the state root hash of a block.
    @dev Reverts for unknown block numbers.
    @param _number Number of the block to look for.
    @return State root hash of Ethereum block.
    """
    state_root: bytes32 = self._checkpoint(_number).stateRoot
    assert state_root != empty(bytes32), "Empty state root"

    return state_root


@external
@view
def find_known_block_number(_before: uint256 = 0) -> uint256:
    """
    @notice Find known block number, not optimized for on-chain use.
        No guarantee to be the last available block.
    @dev Reverts if couldn't find. Checkpoints are sparse, so initial search point is required.
    @param _before Max block number to look for (used as init search point).
    @return Number of Ethereum block with known block hash and state root.
    """
    assert _before > 0, "NeedMaxBlock"

    for i: uint256 in range(MAX_LOOKUP):
        if i > _before:
            break
        number: uint256 = _before - i

        # Low-level call, because absence of checkpoint is reported with revert
        success: bool = False
        response: Bytes[96] = empty(Bytes[96])
        success, response = raw_call(
            SIGNAL_SERVICE.address,
            abi_encode(convert(number, uint48), method_id=method_id("getCheckpoint(uint48)")),
            max_outsize=96,
            is_static_call=True,
            revert_on_failure=False,
        )
        if not success or len(response) != 96:
            continue

        checkpoint: Checkpoint = abi_decode(response, Checkpoint)
        if (
            convert(checkpoint.blockNumber, uint256) == number
            and checkpoint.blockHash != empty(bytes32)
            and checkpoint.stateRoot != empty(bytes32)
        ):
            return number
    raise "NotFound"
