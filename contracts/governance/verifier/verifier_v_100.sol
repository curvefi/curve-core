// SPDX-License-Identifier: MIT
pragma solidity 0.8.18;

import {RLPReader} from "./libs/RLPReader.sol";
import {StateProofVerifier as Verifier} from "./libs/StateProofVerifier.sol";

interface IBlockHashOracle {
    function get_block_hash(uint256 _number) external view returns (bytes32);
    function get_state_root(uint256 _number) external view returns (bytes32);
}

interface IRelayer {
    struct Message {
        address target;
        bytes data;
    }

    function relay(uint256 agent, Message[] calldata messages) external;
}

/// @title Message Digest Verifier
/// @author Curve Finance
contract MessageDigestVerifier {
    using RLPReader for bytes;
    using RLPReader for RLPReader.RLPItem;

    event Verify(uint256 indexed agent, IRelayer.Message[] messages);

    address constant BROADCASTER = 0x7BA33456EC00812C6B6BB6C1C3dfF579c34CC2cc;
    bytes32 constant BROADCASTER_HASH =
        keccak256(abi.encodePacked(BROADCASTER));

    uint256 constant OWNERSHIP_AGENT = 1;
    uint256 constant PARAMETER_AGENT = 2;
    uint256 constant EMERGENCY_AGENT = 4;

    address public immutable BLOCK_HASH_ORACLE;
    address public immutable RELAYER;

    mapping (uint256 => uint256) public nonce;

    constructor(address _block_hash_oracle, address _relayer) {
        require(_block_hash_oracle != address(0), "Bad Blockhash Oracle");
        require(_relayer != address(0), "Bad Relayer");
        BLOCK_HASH_ORACLE = _block_hash_oracle;
        RELAYER = _relayer;
    }

    /// Verify a message digest and optionally execute.
    /// @param _agent The agent which produced the execution digest. (1 = OWNERSHIP, 2 = PARAMETER, 4 = EMERGENCY)
    /// @param _messages The sequence of messages to execute.
    /// @param _block_header_rlp The block header of any block in which messages are broadcasted.
    /// @param _proof_rlp The state proof of messages digest.
    function verifyMessagesByBlockHash(
        uint256 _agent,
        IRelayer.Message[] memory _messages,
        bytes memory _block_header_rlp,
        bytes memory _proof_rlp
    ) external {
        Verifier.BlockHeader memory block_header = Verifier.parseBlockHeader(
            _block_header_rlp
        );
        require(block_header.hash != bytes32(0), "Invalid blockhash");
        require(
            block_header.hash ==
                IBlockHashOracle(BLOCK_HASH_ORACLE).get_block_hash(
                    block_header.number
                ),
            "Blockhash mismatch"
        );

        _verifyMessages(_agent, _messages, block_header.stateRootHash, _proof_rlp);
    }

    /// Verify a message digest and optionally execute.
    /// @param _agent The agent which produced the execution digest. (1 = OWNERSHIP, 2 = PARAMETER, 4 = EMERGENCY)
    /// @param _messages The sequence of messages to execute.
    /// @param _block_number Number of the block to use state root hash.
    /// @param _proof_rlp The state proof of messages digest.
    function verifyMessagesByStateRoot(
        uint256 _agent,
        IRelayer.Message[] memory _messages,
        uint256 _block_number,
        bytes memory _proof_rlp
    ) external {
        bytes32 state_root = IBlockHashOracle(BLOCK_HASH_ORACLE).get_state_root(_block_number);
        require(state_root != bytes32(0), "Invalid stateroot");

        _verifyMessages(_agent, _messages, state_root, _proof_rlp);
    }

    function _verifyMessages(
        uint256 _agent,
        IRelayer.Message[] memory _messages,
        bytes32 _state_root,
        bytes memory _proof_rlp
    ) internal {
        require(
            _agent == OWNERSHIP_AGENT ||
                _agent == PARAMETER_AGENT ||
                _agent == EMERGENCY_AGENT,
            "Invalid agent"
        );
        require(_messages.length != 0, "Empty messages");

        // convert _proof_rlp into a list of `RLPItem`s
        RLPReader.RLPItem[] memory proofs = _proof_rlp.toRlpItem().toList();
        require(proofs.length == 3, "Invalid number of proofs");

        // 0th proof is the account proof for the Broadcaster contract
        Verifier.Account memory account = Verifier.extractAccountFromProof(
            BROADCASTER_HASH, // position of the account is the hash of its address
            _state_root,
            proofs[0].toList()
        );
        require(account.exists, "Broadcaster account does not exist");

        uint256 cur_nonce = nonce[_agent];

        Verifier.SlotValue memory slot = Verifier.extractSlotValueFromProof(
            keccak256(
                abi.encode(
                    keccak256( // self.digest[_agent][_chain_id][_nonce]
                        abi.encode(
                            keccak256( // self.digest[_agent][_chain_id]
                                abi.encode(
                                    keccak256(abi.encode(8, _agent)), // self.digest[_agent]
                                    block.chainid
                                )
                            ),
                            cur_nonce
                        )
                    )
                )
            ),
            account.storageRoot,
            proofs[1].toList()
        );

        require(slot.exists && slot.value != 0, "Bad digest slot value");
        require(keccak256(abi.encode(_messages)) == bytes32(slot.value), "Digest not matched");

        Verifier.SlotValue memory deadline = Verifier.extractSlotValueFromProof(
            keccak256(
                abi.encode(
                    keccak256( // self.deadline[_agent][_chain_id][_nonce]
                        abi.encode(
                            keccak256( // self.deadline[_agent][_chain_id]
                                abi.encode(
                                    keccak256(abi.encode(9, _agent)), // self.deadline[_agent]
                                    block.chainid
                                )
                            ),
                            cur_nonce
                        )
                    )
                )
            ),
            account.storageRoot,
            proofs[2].toList()
        );
        require(deadline.exists && deadline.value != 0, "Bad deadline slot value");

        ++nonce[_agent];
        if (block.timestamp <= deadline.value) {
            IRelayer(RELAYER).relay(_agent, _messages);
        }
        emit Verify(_agent, _messages);
    }
}
