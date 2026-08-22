# pragma version 0.3.10
"""
@title CurveXChainLiquidityGaugeFactory
@custom:version 2.0.2
@author Curve.Fi
@license Copyright (c) Curve.Fi, 2020-2024 - all rights reserved
@notice Layer2/Cross-Chain Gauge Factory for Curve CRV emissions and liquidity gauge deployment.
"""

version: public(constant(String[8])) = "2.0.2"


from vyper.interfaces import ERC20

# --- Interfaces ---

interface ChildGauge:
    def initialize(_lp_token: address, _root: address, _manager: address): nonpayable
    def integrate_fraction(_user: address) -> uint256: view
    def user_checkpoint(_user: address) -> bool: nonpayable

interface CallProxy:
    def anyCall(
        _to: address, _data: Bytes[1024], _fallback: address, _to_chain_id: uint256
    ): nonpayable

# --- Constants ---

WEEK: constant(uint256) = 86400 * 7

# Bit masks for packing gauge_data into a single uint256: [last_request (bits 2+) | is_mirrored (bit 1) | is_valid_gauge (bit 0)]
IS_VALID_GAUGE: constant(uint256) = 1
IS_MIRRORED: constant(uint256) = 2
TIMESTAMP_SHIFT: constant(uint256) = 2


# --- Events ---

event DeployedGauge:
    _implementation: indexed(address)
    _lp_token: indexed(address)
    _deployer: indexed(address)
    _salt: bytes32
    _gauge: address

event Minted:
    _user: indexed(address)
    _gauge: indexed(address)
    _new_total: uint256

event UpdateImplementation:
    _old_implementation: address
    _new_implementation: address

event UpdateVotingEscrow:
    _old_voting_escrow: address
    _new_voting_escrow: address

event UpdateRoot:
    _factory: address
    _implementation: address

event UpdateManager:
    _manager: address

event UpdateCallProxy:
    _old_call_proxy: address
    _new_call_proxy: address

event UpdateMirrored:
    _gauge: indexed(address)
    _mirrored: bool

event TransferOwnership:
    _old_owner: address
    _new_owner: address


# --- Storage Variables ---

# CRV token on the child chain (used for minting rewards)
crv: public(ERC20)

# Current gauge implementation address for proxy deployment
get_implementation: public(address)
# Voting escrow oracle address
voting_escrow: public(address)

# Access control
owner: public(address)
future_owner: public(address)
manager: public(address)
deployer: immutable(address) # Address that deployed the contract (used for one-time owner setup)

# Root chain addresses (used for cross-chain functionality)
root_factory: public(address)
root_implementation: public(address)
call_proxy: public(address)

# gauge_data: gauge address -> [last_request (timestamp) | is_mirrored | is_valid_gauge]
gauge_data: public(HashMap[address, uint256])
# user -> gauge -> total CRV minted to user by this gauge
minted: public(HashMap[address, HashMap[address, uint256]])

# Gauge list and mapping
get_gauge_from_lp_token: public(HashMap[address, address])
get_gauge_count: public(uint256)
get_gauge: public(address[max_value(int128)])


# --- Constructor ---

@external
def __init__(_root_factory: address, _root_impl: address, _crv: address):
    """
    @notice Initializes the Factory with root chain parameters and the CRV token address.
    @param _root_factory Root chain factory to anchor to
    @param _root_impl Address of root gauge implementation to calculate mirror address (can be updated)
    @param _crv Bridged CRV token address (might be zero address if not known yet)
    """
    self.crv = ERC20(_crv)

    assert _root_factory != empty(address), "dev: invalid root factory"
    assert _root_impl != empty(address), "dev: invalid root implementation"
    self.root_factory = _root_factory
    self.root_implementation = _root_impl
    log UpdateRoot(_root_factory, _root_impl)

    self.owner = msg.sender
    log TransferOwnership(empty(address), msg.sender)

    self.manager = msg.sender
    log UpdateManager(msg.sender)

    deployer = msg.sender


@external
def set_owner(_owner: address):
    """
    @notice Finalizes ownership transfer from the initial deployer to the designated owner.
    @dev Can only be called once by the immutable deployer address.
    @param _owner The permanent owner address.
    """
    assert msg.sender == deployer, "dev: only deployer"
    assert self.owner == deployer, "dev: ownership already transferred"
    assert _owner != deployer, "dev: new owner cannot be deployer"

    log TransferOwnership(self.owner, _owner)
    self.owner = _owner


@internal
def _psuedo_mint(_gauge: address, _user: address):
    gauge_data: uint256 = self.gauge_data[_gauge]
    assert gauge_data & IS_VALID_GAUGE != 0, "dev: invalid gauge"

    # Extract last request timestamp (in weeks)
    last_request_week: uint256 = gauge_data >> TIMESTAMP_SHIFT / WEEK
    current_week: uint256 = block.timestamp / WEEK

    # Check if the gauge is mirrored and if the cross-chain emissions request is due (once per week).
    if gauge_data & IS_MIRRORED != 0 and last_request_week != current_week:
        # Request cross-chain emission from the root chain (chain ID 1 is assumed Mainnet)
        CallProxy(self.call_proxy).anyCall(
            self,
            _abi_encode(_gauge, method_id=method_id("transmit_emissions(address)")),
            empty(address),
            1, # Root chain ID (e.g., Ethereum Mainnet)
        )

        # Update last request time while preserving the IS_VALID_GAUGE and IS_MIRRORED bits.
        # The new value is the current week's timestamp shifted left by TIMESTAMP_SHIFT (2).
        new_timestamp_part: uint256 = block.timestamp << TIMESTAMP_SHIFT
        
        # Preserve IS_VALID_GAUGE and IS_MIRRORED flags by OR-ing with the current flags (3).
        self.gauge_data[_gauge] = new_timestamp_part | IS_VALID_GAUGE | IS_MIRRORED


    # Perform user checkpoint on the child gauge (required before minting)
    assert ChildGauge(_gauge).user_checkpoint(_user), "dev: checkpoint failed"
    
    # Calculate mintable amount
    total_mint: uint256 = ChildGauge(_gauge).integrate_fraction(_user)
    to_mint: uint256 = total_mint - self.minted[_user][_gauge]

    # Transfer CRV rewards if the amount is non-zero and the CRV address is set.
    if to_mint != 0 and self.crv != empty(ERC20):
        assert self.crv.transfer(_user, to_mint, default_return_value=True), "dev: CRV transfer failed"
        self.minted[_user][_gauge] = total_mint

        log Minted(_user, _gauge, total_mint)


@external
@nonreentrant("lock")
def mint(_gauge: address):
    """
    @notice Mints available CRV emissions for `msg.sender` from a single gauge.
    @param _gauge `LiquidityGauge` address to get mintable amount from
    """
    self._psuedo_mint(_gauge, msg.sender)


@external
@nonreentrant("lock")
def mint_many(_gauges: address[32]):
    """
    @notice Mints available CRV emissions for `msg.sender` across multiple gauges.
    @param _gauges List of up to 32 `LiquidityGauge` addresses
    """
    for i in range(32):
        gauge: address = _gauges[i]
        if gauge != empty(address):
            self._psuedo_mint(gauge, msg.sender)


@external
def deploy_gauge(_lp_token: address, _salt: bytes32, _manager: address = msg.sender) -> address:
    """
    @notice Deploy a new liquidity gauge via a minimal proxy and compute the root gauge address.
    @param _lp_token The token (pool token) to deposit in the gauge
    @param _salt A value to deterministically deploy the gauge
    @param _manager The address to set as manager of the gauge (defaults to msg.sender)
    @return The address of the newly deployed gauge
    """
    if self.get_gauge_from_lp_token[_lp_token] != empty(address):
        # Allow owner to overwrite the lp_token -> gauge mapping, typically for redeployments/fixes.
        assert msg.sender == self.owner, "dev: only owner can overwrite existing gauge mapping"

    gauge_data: uint256 = IS_VALID_GAUGE # Initial state: gauge is valid
    implementation: address = self.get_implementation
    
    # Keccak256 salt with chain ID to ensure cross-chain address determinism.
    salt: bytes32 = keccak256(_abi_encode(chain.id, _salt))
    
    # Deploy the gauge using the minimal proxy pattern (CREATE2 derivation).
    gauge: address = create_minimal_proxy_to(
        implementation, salt=salt
    )

    if msg.sender == self.call_proxy:
        gauge_data |= IS_MIRRORED  # Set is_mirrored = True
        log UpdateMirrored(gauge, True)
        
        # Issue a call back to the root chain (ID 1) to deploy a corresponding root gauge.
        CallProxy(self.call_proxy).anyCall(
            self.root_factory,
            _abi_encode(chain.id, _salt, method_id=method_id("deploy_gauge(uint256,bytes32)")),
            empty(address),
            1 # Root chain ID
        )

    self.gauge_data[gauge] = gauge_data

    idx: uint256 = self.get_gauge_count
    self.get_gauge[idx] = gauge
    self.get_gauge_count = idx + 1
    self.get_gauge_from_lp_token[_lp_token] = gauge

    # --- Root Gauge Address Derivation (EIP-1014) ---
    # This complex derivation relies on the minimal proxy bytecode of the root implementation.
    gauge_codehash: bytes32 = keccak256(
        concat(
            0x602d3d8160093d39f3363d3d373d3d3d363d73,
            convert(self.root_implementation, bytes20),
            0x5af43d82803e903d91602b57fd5bf3,
        )
    )
    # The digest is computed using the Root Factory address and the same salt.
    digest: bytes32 = keccak256(concat(0xFF, convert(self.root_factory, bytes20), salt, gauge_codehash))
    root: address = convert(convert(digest, uint256) & convert(max_value(uint160), uint256), address)
    
    # Initialize the deployed child gauge.
    ChildGauge(gauge).initialize(_lp_token, root, _manager)

    log DeployedGauge(implementation, _lp_token, msg.sender, _salt, gauge)
    return gauge


@external
def set_crv(_crv: ERC20):
    """
    @notice Sets CRV token address. Cannot be called if CRV is already set.
    @dev Child gauges reference the factory to fetch the CRV address.
    @param _crv address of CRV token on child chain
    """
    assert msg.sender == self.owner, "dev: only owner"
    assert _crv != empty(ERC20), "dev: invalid CRV address"
    assert self.crv == empty(ERC20), "dev: CRV already set"

    self.crv = _crv


@external
def set_root(_factory: address, _implementation: address):
    """
    @notice Update root addresses.
    @dev Addresses are used as helper methods for address derivation.
    @param _factory Root gauge factory
    @param _implementation Root gauge implementation
    """
    assert msg.sender in [self.owner, self.manager], "dev: access denied"

    self.root_factory = _factory
    self.root_implementation = _implementation
    log UpdateRoot(_factory, _implementation)


@external
def set_voting_escrow(_voting_escrow: address):
    """
    @notice Update the voting escrow contract used as an oracle.
    @param _voting_escrow Contract address
    """
    assert msg.sender == self.owner, "dev: only owner"

    log UpdateVotingEscrow(self.voting_escrow, _voting_escrow)
    self.voting_escrow = _voting_escrow


@external
def set_implementation(_implementation: address):
    """
    @notice Set the address of the child gauge implementation to be deployed via proxy.
    @param _implementation The address of the implementation to use
    """
    assert msg.sender == self.owner, "dev: only owner"

    log UpdateImplementation(self.get_implementation, _implementation)
    self.get_implementation = _implementation


@external
def set_mirrored(_gauge: address, _mirrored: bool):
    """
    @notice Explicitly set the mirrored status of a gauge.
    @dev Used primarily for fixing broken cross-chain state.
    @param _gauge The gauge of interest
    @param _mirrored Boolean determining whether the mirrored bit is set.
    """
    gauge_data: uint256 = self.gauge_data[_gauge]
    assert gauge_data & IS_VALID_GAUGE != 0, "dev: invalid gauge"
    assert msg.sender == self.owner, "dev: only owner"

    # Mask off the IS_MIRRORED bit first.
    gauge_data &= (max_value(uint256) - IS_MIRRORED)
    
    if _mirrored:
        gauge_data |= IS_MIRRORED # Set the mirrored bit if True

    self.gauge_data[_gauge] = gauge_data
    log UpdateMirrored(_gauge, _mirrored)


@external
def set_call_proxy(_new_call_proxy: address):
    """
    @notice Set the address of the cross-chain call proxy used for communication.
    @param _new_call_proxy Address of the cross chain call proxy
    """
    assert msg.sender == self.owner, "dev: only owner"

    log UpdateCallProxy(self.call_proxy, _new_call_proxy)
    self.call_proxy = _new_call_proxy


@external
def set_manager(_new_manager: address):
    """
    @notice Set the manager address, which has partial control rights.
    @param _new_manager Address of the new manager
    """
    assert msg.sender in [self.owner, self.manager], "dev: access denied"

    self.manager = _new_manager
    log UpdateManager(_new_manager)


@external
def commit_transfer_ownership(_future_owner: address):
    """
    @notice Initiates the transfer of contract ownership to `_future_owner`.
    @param _future_owner The account to commit as the future owner
    """
    assert msg.sender == self.owner, "dev: only owner"

    self.future_owner = _future_owner


@external
def accept_transfer_ownership():
    """
    @notice Completes the transfer of ownership.
    @dev Only the committed future owner can call this function.
    """
    assert msg.sender == self.future_owner, "dev: only future owner"

    log TransferOwnership(self.owner, msg.sender)
    self.owner = msg.sender


# --- View Functions for Gauge Data ---

@view
@external
def is_valid_gauge(_gauge: address) -> bool:
    """
    @notice Query whether the gauge is a valid one deployed via the factory.
    @param _gauge The address of the gauge of interest
    """
    return self.gauge_data[_gauge] & IS_VALID_GAUGE != 0


@view
@external
def is_mirrored(_gauge: address) -> bool:
    """
    @notice Query whether the gauge is mirrored on the root chain.
    @param _gauge The address of the gauge of interest
    """
    return self.gauge_data[_gauge] & IS_MIRRORED != 0


@view
@external
def last_request(_gauge: address) -> uint256:
    """
    @notice Query the timestamp of the last cross-chain request for emissions.
    @param _gauge The address of the gauge of interest
    """
    # Shift right to isolate the timestamp part of the packed data.
    return self.gauge_data[_gauge] >> TIMESTAMP_SHIFT
