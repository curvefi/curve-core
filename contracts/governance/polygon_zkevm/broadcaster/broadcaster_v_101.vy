# @version 0.3.10
"""
@title Polygon zkEVM Broadcaster
@author CurveFi
@license MIT
@custom:version 1.0.1
"""

version: public(constant(String[8])) = "1.0.1"


interface PolygonZkEVMBridge:
    def bridgeMessage(destination_network: uint32, destination_address: address, force_update: bool, metadata: Bytes[MAX_MESSAGE_RECEIVED]): payable


event Broadcast:
    agent: Agent
    messages: DynArray[Message, MAX_MESSAGES]


event SetNewBridge:
    new_bridge: PolygonZkEVMBridge


event SetNewDestinationNetwork:
    new_network: uint32


event ApplyAdmins:
    admins: AdminSet

event CommitAdmins:
    future_admins: AdminSet


enum Agent:
    OWNERSHIP
    PARAMETER
    EMERGENCY


struct AdminSet:
    ownership: address
    parameter: address
    emergency: address

struct Message:
    target: address
    data: Bytes[MAX_BYTES]


MAX_BYTES: constant(uint256) = 1024
MAX_MESSAGES: constant(uint256) = 8
MAX_MESSAGE_RECEIVED: constant(uint256) = 9400


admins: public(AdminSet)
future_admins: public(AdminSet)

agent: public(HashMap[address, Agent])

POLYGON_ZKEVM_BRIDGE: public(immutable(PolygonZkEVMBridge))
DESTINATION_NETWORK: public(immutable(uint32))


@external
def __init__(_admins: AdminSet, _polygon_zkevm_bridge: PolygonZkEVMBridge, _destination_network: uint32):
    assert _admins.ownership != _admins.parameter  # a != b
    assert _admins.ownership != _admins.emergency  # a != c
    assert _admins.parameter != _admins.emergency  # b != c

    self.admins = _admins

    self.agent[_admins.ownership] = Agent.OWNERSHIP
    self.agent[_admins.parameter] = Agent.PARAMETER
    self.agent[_admins.emergency] = Agent.EMERGENCY

    POLYGON_ZKEVM_BRIDGE = _polygon_zkevm_bridge
    DESTINATION_NETWORK = _destination_network

    log ApplyAdmins(_admins)


@external
def broadcast(_messages: DynArray[Message, MAX_MESSAGES], _force_update: bool=True):
    """
    @notice Broadcast a sequence of messages.
    @dev Save `depositCount` from POLYGON_ZKEVM_BRIDGE.BridgeEvent to claim message on destination chain
    @param _messages The sequence of messages to broadcast.
    @param _force_update Indicates if the new global exit root is updated or not (forceUpdateGlobalExitRoot)
    """
    agent: Agent = self.agent[msg.sender]
    assert agent != empty(Agent)

    POLYGON_ZKEVM_BRIDGE.bridgeMessage(DESTINATION_NETWORK, self, _force_update,
        _abi_encode(  # relay(uint256,(address,bytes)[])
            agent,
            _messages,
            method_id=method_id("relay(uint256,(address,bytes)[])"),
        ),
    )

    log Broadcast(agent, _messages)


@external
def commit_admins(_future_admins: AdminSet):
    """
    @notice Commit an admin set to use in the future.
    """
    assert msg.sender == self.admins.ownership

    assert _future_admins.ownership != _future_admins.parameter  # a != b
    assert _future_admins.ownership != _future_admins.emergency  # a != c
    assert _future_admins.parameter != _future_admins.emergency  # b != c

    self.future_admins = _future_admins
    log CommitAdmins(_future_admins)


@external
def apply_admins():
    """
    @notice Apply the future admin set.
    """
    admins: AdminSet = self.admins
    assert msg.sender == admins.ownership

    # reset old admins
    self.agent[admins.ownership] = empty(Agent)
    self.agent[admins.parameter] = empty(Agent)
    self.agent[admins.emergency] = empty(Agent)

    # set new admins
    future_admins: AdminSet = self.future_admins
    self.agent[future_admins.ownership] = Agent.OWNERSHIP
    self.agent[future_admins.parameter] = Agent.PARAMETER
    self.agent[future_admins.emergency] = Agent.EMERGENCY

    self.admins = future_admins
    log ApplyAdmins(future_admins)
