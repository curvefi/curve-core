#!/usr/bin/python3

from brownie import network
from brownie import StableCalcZap, accounts, ZERO_ADDRESS
from eth_abi import encode


INIT_DATA = {
    "ethereum": {
        "use_int128": [
            "0xA2B47E3D5c44877cca798226B7B8118F9BFb7A56",  # compound
            "0x52EA46506B9CC5Ef470C5bf89f17Dc28bB35D85C",  # usdt
            "0x45F783CCE6B7FF23B2ab2D70e416cdb7D6055f51",  # y
            "0x79a8C46DeA5aDa233ABaFFD40F3A0A2B1e5A4F27",  # busd
            "0xA5407eAE9Ba41422680e2e00537571bcC53efBfD",  # susd
            "0x06364f10B501e868329afBc005b3492902d6C763",  # pax
            "0x93054188d876f558f4a66B2EF1d97d16eDf0895B",  # ren
            "0x7fC77b5c7614E1533320Ea6DDc2Eb61fa00A9714",  # sbtc
        ],
        "pool_type_addresses": [
            "0x618788357D0EBd8A37e763ADab3bc575D54c2C7d",  # rai

            "0xDeBF20617708857ebe4F679508E7b7863a8A8EeE",  # aave
            "0xeb16ae0052ed37f479f7fe63849198df1765a733",  # saave

            "0x2dded6Da1BF5DBdF597C45fcFaa3194e53EcfeAF",  # ib
            "0x52EA46506B9CC5Ef470C5bf89f17Dc28bB35D85C",  # usdt
            "0xA2B47E3D5c44877cca798226B7B8118F9BFb7A56",  # compound

            "0x45F783CCE6B7FF23B2ab2D70e416cdb7D6055f51",  # y
            "0x79a8C46DeA5aDa233ABaFFD40F3A0A2B1e5A4F27",  # busd
            "0x06364f10B501e868329afBc005b3492902d6C763",  # pax

            "0xA96A65c051bF88B4095Ee1f2451C2A9d43F53Ae2",  # aETH

            "0xF9440930043eb3997fc70e1339dBb11F341de7A8",  # rETH

            "0xBfAb6FA95E0091ed66058ad493189D2cB29385E6",  # wBETH
        ],
        "pool_types": [
            2,  # rai

            3,  # aave
            3,  # saave

            4,  # ib
            4,  # usdt
            4,  # compound

            6,  # y
            6,  # busd
            6,  # pax

            7,  # aETH

            8,  # rETH

            10,  # wBETH
        ],
        "use_rate": [
            [True, False, False, False, False],   # rai

            [False, False, False, False, False],  # aave
            [False, False, False, False, False],  # saave

            [True, True, True, False, False],     # ib
            [True, True, False, False, False],    # usdt
            [True, True, False, False, False],    # compound

            [True, True, True, True, False],      # y
            [True, True, True, True, False],      # busd
            [True, True, True, False, False],     # pax

            [False, True, False, False, False],   # aETH

            [False, True, False, False, False],   # rETH

            [False, True, False, False, False],   # wBETH
        ],
        "stored_rates_implementations": [
            # [factory_address, implementation_address]
            ["0xb9fc157394af804a3578134a6585c0dc9cc990d4", "0x847ee1227A9900B73aEeb3a47fAc92c52FD54ed9"],
            ["0x4F8846Ae9380B90d2E71D5e3D042dff3E7ebb40d", "0x36Dc03C0e12a1C241306a6A8F327Fe28bA2Be5b0"],
        ],
    },
    "optimism": {
        "use_int128": [],
        "pool_type_addresses": [
            "0xB90B9B1F91a01Ea22A182CD84C1E22222e39B415",  # wstETH
        ],
        "pool_types": [
            9,  # wstETH
        ],
        "use_rate": [
            [False, True, False, False, False],   # wstETH
        ],
        "stored_rates_implementations": [["0x2db0E83599a91b508Ac268a6197b8B14F5e72840", "0x6F9fb833501f46CBE6f6A4b6Cf32C834E5A5e8C5"]],
    },
    "xdai": {
        "use_int128": [],
        "pool_type_addresses": [
            "0x85bA9Dfb4a3E4541420Fc75Be02E2B42042D7e46",  # rai
        ],
        "pool_types": [
            2,  # rai
        ],
        "use_rate": [
            [True, False, False, False, False],   # rai
        ],
        "stored_rates_implementations": [],
    },
    "polygon": {
        "use_int128": [],
        "pool_type_addresses": [
            "0x445FE580eF8d70FF569aB36e80c647af338db351",  # aave
        ],
        "pool_types": [
            3,  # aave
        ],
        "use_rate": [
            [False, False, False, False, False],   # aave
        ],
        "stored_rates_implementations": [],
    },
    "fantom": {
        "use_int128": [],
        "pool_type_addresses": [
            "0x0fa949783947Bf6c1b171DB13AEACBB488845B3f",  # geist

            "0x4FC8D635c3cB1d0aa123859e2B2587d0FF2707b1",  # ib
        ],
        "pool_types": [
            3,  # geist

            5,  # ib
        ],
        "use_rate": [
            [False, False, False, False, False],  # geist

            [True, True, True, False, False],     # ib
        ],
        "stored_rates_implementations": [],
    },
    "moonbeam": {
        "use_int128": [],
        "pool_type_addresses": [],
        "pool_types": [],
        "use_rate": [],
        "stored_rates_implementations": [],
    },
    "kava": {
        "use_int128": [],
        "pool_type_addresses": [],
        "pool_types": [],
        "use_rate": [],
        "stored_rates_implementations": [],
    },
    "arbitrum": {
        "use_int128": [],
        "pool_type_addresses": [
            "0x6eB2dc694eB516B16Dc9FBc678C60052BbdD7d80",  # wstETH
        ],
        "pool_types": [
            9,  # wstETH
        ],
        "use_rate": [
            [False, True, False, False, False],   # wstETH
        ],
        "stored_rates_implementations": [["0xb17b674D9c5CB2e441F8e196a2f048A81355d031", "0x6F9fb833501f46CBE6f6A4b6Cf32C834E5A5e8C5"]],
    },
    "celo": {
        "use_int128": [],
        "pool_type_addresses": [],
        "pool_types": [],
        "use_rate": [],
        "stored_rates_implementations": [],
    },
    "avalanche": {
        "use_int128": [],
        "pool_type_addresses": [
            "0x7f90122BF0700F9E7e1F688fe926940E8839F353",  # aave
            "0xD2AcAe14ae2ee0f6557aC6C6D0e407a92C36214b",  # aaveV3
        ],
        "pool_types": [
            3,  # aave
            3,  # aaveV3
        ],
        "use_rate": [
            [False, False, False, False, False],   # aave
            [False, False, False, False, False],   # aaveV3
        ],
        "stored_rates_implementations": [],
    },
    "aurora": {
        "use_int128": [],
        "pool_type_addresses": [],
        "pool_types": [],
        "use_rate": [],
        "stored_rates_implementations": [],
    },
    "base": {
        "use_int128": [],
        "pool_type_addresses": [],
        "pool_types": [],
        "use_rate": [],
        "stored_rates_implementations": [],
    },
    "bsc": {
        "use_int128": [],
        "pool_type_addresses": [],
        "pool_types": [],
        "use_rate": [],
        "stored_rates_implementations": [],
    },
    "fraxtal": {
        "use_int128": [],
        "pool_type_addresses": [],
        "pool_types": [],
        "use_rate": [],
        "stored_rates_implementations": [],
    },
    "xlayer": {
        "use_int128": [],
        "pool_type_addresses": [],
        "pool_types": [],
        "use_rate": [],
        "stored_rates_implementations": [],
    },
}


def main():
    max_coins = 10
    txparams = {}
    network_name = network.show_active()
    if network_name == 'mainnet':
        network_name = 'ethereum'
    if network_name == 'ethereum':
        accounts.load('curve-deployer')
        txparams.update({'priority_fee': '2 gwei'})
    elif not network_name.endswith("-fork"):
        accounts.load('curve-deployer')

    use_int128 = INIT_DATA[network_name]["use_int128"]
    pool_type_addresses = INIT_DATA[network_name]["pool_type_addresses"]
    pool_types = INIT_DATA[network_name]["pool_types"]
    use_rate = INIT_DATA[network_name]["use_rate"]
    stored_rates_implementations = INIT_DATA[network_name]["stored_rates_implementations"]

    use_int128 += [ZERO_ADDRESS] * (20 - len(use_int128))
    pool_type_addresses += [ZERO_ADDRESS] * (20 - len(pool_type_addresses))
    pool_types += [0] * (20 - len(pool_types))
    use_rate = [x + [False] * (max_coins - len(x)) for x in use_rate]
    use_rate += [[False] * max_coins] * (20 - len(use_rate))

    txparams.update({'from': accounts[0]})
    return StableCalcZap.deploy(use_int128, pool_type_addresses, pool_types, use_rate, stored_rates_implementations, txparams)
