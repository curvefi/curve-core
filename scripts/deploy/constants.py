from enum import Enum

from eth_utils import keccak

from settings.config import RollupType

MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"
CREATE2_SALT = keccak(42069)
CREATE2DEPLOYER_ADDRESS = "0x13b0D85CcB8bf860b6b79AF3029fCA081AE9beF2"
CREATE2DEPLOYER_ABI = """
[
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": true,
          "internalType": "address",
          "name": "previousOwner",
          "type": "address"
        },
        {
          "indexed": true,
          "internalType": "address",
          "name": "newOwner",
          "type": "address"
        }
      ],
      "name": "OwnershipTransferred",
      "type": "event"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": false,
          "internalType": "address",
          "name": "account",
          "type": "address"
        }
      ],
      "name": "Paused",
      "type": "event"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": false,
          "internalType": "address",
          "name": "account",
          "type": "address"
        }
      ],
      "name": "Unpaused",
      "type": "event"
    },
    {
      "inputs": [
        {
          "internalType": "bytes32",
          "name": "salt",
          "type": "bytes32"
        },
        {
          "internalType": "bytes32",
          "name": "codeHash",
          "type": "bytes32"
        }
      ],
      "name": "computeAddress",
      "outputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "bytes32",
          "name": "salt",
          "type": "bytes32"
        },
        {
          "internalType": "bytes32",
          "name": "codeHash",
          "type": "bytes32"
        },
        {
          "internalType": "address",
          "name": "deployer",
          "type": "address"
        }
      ],
      "name": "computeAddressWithDeployer",
      "outputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "stateMutability": "pure",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "uint256",
          "name": "value",
          "type": "uint256"
        },
        {
          "internalType": "bytes32",
          "name": "salt",
          "type": "bytes32"
        },
        {
          "internalType": "bytes",
          "name": "code",
          "type": "bytes"
        }
      ],
      "name": "deploy",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "uint256",
          "name": "value",
          "type": "uint256"
        },
        {
          "internalType": "bytes32",
          "name": "salt",
          "type": "bytes32"
        }
      ],
      "name": "deployERC1820Implementer",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address payable",
          "name": "payoutAddress",
          "type": "address"
        }
      ],
      "name": "killCreate2Deployer",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "owner",
      "outputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "pause",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "paused",
      "outputs": [
        {
          "internalType": "bool",
          "name": "",
          "type": "bool"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "renounceOwnership",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "newOwner",
          "type": "address"
        }
      ],
      "name": "transferOwnership",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "unpause",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "stateMutability": "payable",
      "type": "receive"
    }
  ]
"""
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


ETHEREUM_ADMINS = (
    "0x40907540d8a6C65c637785e8f8B742ae6b0b9968",  # Ownership
    "0x4EEb3bA4f221cA16ed4A0cC7254E2E32DF948c5f",  # Parameter
    "0x467947EE34aF926cF1DCac093870f613C96B1E0c",  # Emergency
)

BROADCASTERS = {
    RollupType.op_stack: "0xE0fE4416214e95F0C67Dc044AAf1E63d6972e0b9",
    RollupType.polygon_cdk: "0xB5e7fE8eA8ECbd33504485756fCabB5f5D29C051",
    RollupType.arb_orbit: "0x94630a56519c00Be339BBd8BD26f342Bf4bd7eE0",
}

ROOT_GAUGE_FACTORY = "0x306A45a1478A000dC701A6e1f7a569afb8D9DCD6"
ROOT_GAUGE_IMPLEMENTATION = "0x96720942F9fF22eFd8611F696E5333Fe3671717a"  # ROOT_GAUGE_FACTORY.get_implementation()


class AddressProviderID(Enum):
    EXCHANGE_ROUTER = (2, "Exchange Router")
    FEE_DISTRIBUTOR = (4, "Fee Distributor")
    METAREGISTRY = (7, "Metaregistry")
    TRICRYPTONG_FACTORY = (11, "TricryptoNG Factory")
    STABLESWAPNG_FACTORY = (12, "StableswapNG Factory")
    TWOCRYPTONG_FACTORY = (13, "TwocryptoNG Factory")
    SPOT_RATE_PROVIDER = (18, "Spot Rate Provider")
    GAUGE_FACTORY = (20, "Gauge Factory")
    OWNERSHIP_ADMIN = (21, "Ownership Admin")
    PARAMETER_ADMIN = (22, "Parameter Admin")
    EMERGENCY_ADMIN = (23, "Emergency Admin")
    CURVEDAO_VAULT = (24, "CurveDAO Vault")
    DEPOSIT_AND_STAKE_ZAP = (26, "Deposit and Stake Zap")
    STABLESWAP_META_ZAP = (27, "Stableswap Meta Zap")
    CRV_TOKEN = (19, "CRV Token")
    CRVUSD_TOKEN = (25, "crvUSD Token")

    def __init__(self, id, description):
        self.id = id
        self.description = description
