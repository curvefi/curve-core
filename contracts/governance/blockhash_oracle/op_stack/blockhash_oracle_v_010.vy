# pragma version 0.4.0
"""
@title Optimism Block Hash oracle
@notice A contract that saves L1 block hashes.
@license MIT
@author curve.fi
@custom:version 0.1.0
@custom:security security@curve.fi
"""

from contracts.governance.blockhash_oracle import IBlockHashOracle
from contracts.governance.blockhash_oracle import IBlockHashRetain

implements: IBlockHashOracle
implements: IBlockHashRetain

version: public(constant(String[8])) = "0.1.0"


interface IL1Block:
    def number() -> uint64: view
    def hash() -> bytes32: view


L1_BLOCK: constant(IL1Block) = IL1Block(0x4200000000000000000000000000000000000015)

MAX_LOOKUP: constant(uint256) = 7 * 86400  # A week

block_hash: public(HashMap[uint256, bytes32])
commitments: public(HashMap[address, HashMap[uint256, bytes32]])

last_applied: uint256


@view
@external
def get_block_hash(_number: uint256) -> bytes32:
    """
    @notice Query the block hash of a block.
    @dev Reverts for unknown block numbers or if not supported.
    @param _number Number of the block to look for.
    """
    block_hash: bytes32 = self.block_hash[_number]
    if block_hash == empty(bytes32) and _number == convert(staticcall L1_BLOCK.number(), uint256):
        # try fetching current data
        block_hash = staticcall L1_BLOCK.hash()
    assert block_hash != empty(bytes32)

    return block_hash


@view
@external
def get_state_root(_number: uint256) -> bytes32:
    """
    @notice Query the state root hash of a block.
    @dev Reverts for unknown block numbers or if not supported.
    @param _number Number of the block to look for.
    """
    raise "NotImplemented"


@view
@external
def find_known_block_number(_before: uint256 = 0) -> uint256:
    """
    @notice Find known block number, not optimized for on-chain use.
        No guarantee to be the last available block.
    @dev Reverts if not supported or couldn't find.
    @param _before Max block number to look for (can be used as init search point).
    """
    last_applied: uint256 = self.last_applied
    if _before == 0 or last_applied < _before:
        return last_applied

    for i: uint256 in range(MAX_LOOKUP):
        if self.block_hash[_before - i] != empty(bytes32):
            return _before - i
    raise "NotFound"


@internal
def _update_block_hash() -> (uint256, bytes32):
    number: uint256 = convert(staticcall L1_BLOCK.number(), uint256)
    hash: bytes32 = staticcall L1_BLOCK.hash()
    self.block_hash[number] = hash

    self.last_applied = max(self.last_applied, number)
    return number, hash


@external
def commit() -> uint256:
    """
    @notice Commit (and apply) a block hash.
    @dev Same as `apply()` but saves committer
    """
    number: uint256 = 0
    hash: bytes32 = empty(bytes32)
    number, hash = self._update_block_hash()

    self.commitments[msg.sender][number] = hash
    log IBlockHashRetain.CommitBlockHash(msg.sender, number, hash)
    log IBlockHashRetain.ApplyBlockHash(number, hash)
    return number


@external
def apply() -> uint256:
    """
    @notice Apply a block hash.
    """
    number: uint256 = 0
    hash: bytes32 = empty(bytes32)
    number, hash = self._update_block_hash()

    log IBlockHashRetain.ApplyBlockHash(number, hash)
    return number
