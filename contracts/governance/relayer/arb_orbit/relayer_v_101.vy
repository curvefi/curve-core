# pragma version 0.3.10
"""
@title Arbitrum Relayer
@author CurveFi
@license MIT
@custom:version 1.0.1
"""

# Version constant matching the docstring version.
version: public(constant(String[8])) = "1.0.1"


# --- INTERFACES ---

# Interface for the execution agents (Ownership, Parameter, Emergency).
interface IAgent:
    def execute(_messages: DynArray[Message, MAX_MESSAGES]): nonpayable

# Interface for the Arbitrum system contract, used to check L1 origin.
interface IArbSys:
    # Returns true if the caller's L1 address has been aliased to an L2 address.
    def wasMyCallersAddressAliased() -> bool: view
    # Returns the L1 address that initiated the call.
    def myCallersAddressWithoutAliasing() -> address: view


# --- STORAGE AND CONSTANTS ---

# Enum to define the distinct roles for agents.
enum Agent:
    OWNERSHIP
    PARAMETER
    EMERGENCY


# Structure representing a single message to be relayed.
struct Message:
    target: address
    data: Bytes[MAX_BYTES]


MAX_BYTES: constant(uint256) = 1024       # Maximum bytes for a single message payload.
MAX_MESSAGES: constant(uint256) = 8      # Maximum messages allowed in one relay transaction.
CODE_OFFSET: constant(uint256) = 3       # Code offset for create_from_blueprint (implementation specific).


# Immutable addresses set during deployment.
BROADCASTER: public(immutable(address))  # The trusted L1 address initiating the relay.
ARBSYS: public(immutable(address))       # Arbitrum System contract address.

# Centralized mapping for quick lookup of deployed agent addresses by role.
# This replaces the need for individual immutable address variables.
agent: public(HashMap[Agent, address])


# --- EXTERNAL FUNCTIONS ---

@external
def __init__(broadcaster: address, _agent_blueprint: address, _arbsys: address):
    """
    Initializes the Relayer, sets the trusted addresses, and deploys the agent contracts 
    from the provided blueprint address.
    """
    BROADCASTER = broadcaster
    ARBSYS = _arbsys

    # Deploy all three execution agents from the blueprint.
    ownership_agent_addr: address = create_from_blueprint(_agent_blueprint, code_offset=CODE_OFFSET)
    parameter_agent_addr: address = create_from_blueprint(_agent_blueprint, code_offset=CODE_OFFSET)
    emergency_agent_addr: address = create_from_blueprint(_agent_blueprint, code_offset=CODE_OFFSET)

    # Store the deployed addresses in the public agent map.
    self.agent[Agent.OWNERSHIP] = ownership_agent_addr
    self.agent[Agent.PARAMETER] = parameter_agent_addr
    self.agent[Agent.EMERGENCY] = emergency_agent_addr


@external
def relay(_agent: Agent, _messages: DynArray[Message, MAX_MESSAGES]):
    """
    @notice Receives messages for an agent and securely relays them.
    @dev Only callable from the trusted BROADCASTER L1 address via the L1->L2 bridge.
    @param _agent The agent (role) to relay messages to.
    @param _messages The sequence of messages (target + data) to relay.
    """
    # 1. SECURITY CHECK: Ensure the call originated from an L1 address (aliased).
    assert IArbSys(ARBSYS).wasMyCallersAddressAliased(), "Relayer: Call must originate from L1"
    
    # 2. SECURITY CHECK: Ensure the L1 origin address is the trusted BROADCASTER.
    assert IArbSys(ARBSYS).myCallersAddressWithoutAliasing() == BROADCASTER, "Relayer: Untrusted L1 caller"

    # 3. EXECUTION: Execute the messages on the specific agent contract.
    IAgent(self.agent[_agent]).execute(_messages)
