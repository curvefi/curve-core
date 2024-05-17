#!/usr/bin/python3

from brownie import network, ZERO_ADDRESS
from brownie import Router, RouterOptimism, RouterSidechain, RouterSidechainTricryptoMeta, accounts


# Skip Celo and Aurora
INIT_DATA = {
    "ethereum": {
        "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "crypto_calc": "0xA72C85C258A81761433B4e8da60505Fe3Dd551CC",
        "snx_coins": [
            "0x57Ab1ec28D129707052df4dF418D58a2D46d5f51",  # sUSD
            "0xD71eCFF9342A5Ced620049e616c5035F1dB98620",  # sEUR
            "0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb",  # sETH
            "0xfE18be6b3Bd88A2D2A7f928d00292E7a9963CfC6",  # sBTC
        ]
    },
    "optimism": {
        "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "crypto_calc": "0xA72C85C258A81761433B4e8da60505Fe3Dd551CC",
        "snx_coins": [
            "0x8c6f28f2f1a3c87f0f938b96d27520d9751ec8d9",  # sUSD
            "0xFBc4198702E81aE77c06D58f81b629BDf36f0a71",  # sEUR
            "0xe405de8f52ba7559f9df3c368500b6e6ae6cee49",  # sETH
            "0x298b9b95708152ff6968aafd889c6586e9169f1d",  # sBTC
        ]
    },
    "xdai": {
        "tricrypto_meta_pools": ["0x5633E00994896D0F472926050eCb32E38bef3e65", ZERO_ADDRESS],  # tricrypto
        "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "crypto_calc": "0xA72C85C258A81761433B4e8da60505Fe3Dd551CC",
    },
    "polygon": {
        "tricrypto_meta_pools": ["0x92215849c439E1f8612b6646060B4E3E5ef822cC", ZERO_ADDRESS],  # atricrypto3
        "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "crypto_calc": "0xA72C85C258A81761433B4e8da60505Fe3Dd551CC",
    },
    "fantom": {
        "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "crypto_calc": "0xA72C85C258A81761433B4e8da60505Fe3Dd551CC",
    },
    # "zksync": {  TODO
    #     "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",  TODO deploy stable_calc
    #     "crypto_calc": "0xA72C85C258A81761433B4e8da60505Fe3Dd551CC",  TODO deploy crypto_calc
    # },
    # "moonbeam": {  TODO
    #     "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
    #     "crypto_calc": "0xA72C85C258A81761433B4e8da60505Fe3Dd551CC",
    # },
    "kava": {
        "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "crypto_calc": "0xA72C85C258A81761433B4e8da60505Fe3Dd551CC",
    },
    "base": {
        "stable_calc": "0x5552b631e2aD801fAa129Aacf4B701071cC9D1f7",
        "crypto_calc": "0xEfadDdE5B43917CcC738AdE6962295A0B343f7CE",
    },
    "arbitrum": {
        "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "crypto_calc": "0xA72C85C258A81761433B4e8da60505Fe3Dd551CC",
    },
    "avalanche": {
        "tricrypto_meta_pools": ["0xB755B949C126C04e0348DD881a5cF55d424742B2", "0x204f0620e7e7f07b780535711884835977679bba"],  # atricrypto, avaxcrypto
        "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "crypto_calc": "0xA72C85C258A81761433B4e8da60505Fe3Dd551CC",
    },
    "bsc": {
        "stable_calc": "0x0fE38dCC905eC14F6099a83Ac5C93BF2601300CF",
        "crypto_calc": "0xd6681e74eea20d196c15038c580f721ef2ab6320",
    },
    "fraxtal": {
        "stable_calc": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "crypto_calc": "0x69522fb5337663d3B4dFB0030b881c1A750Adb4f",
    },
    "xlayer": {
        "stable_calc": "0x0fE38dCC905eC14F6099a83Ac5C93BF2601300CF",
        "crypto_calc": "0x69522fb5337663d3B4dFB0030b881c1A750Adb4f",
    },
}

WETH = {
    "ethereum": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    "optimism": "0x4200000000000000000000000000000000000006",
    "xdai": "0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d",
    "polygon": "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270",
    "fantom": "0x21be370D5312f44cB42ce377BC9b8a0cEF1A4C83",
    "zksync": "0x5AEa5775959fBC2557Cc8789bC1bf90A239D9a91",
    "moonbeam": "0xAcc15dC74880C9944775448304B263D191c6077F",
    "kava": "0xc86c7C0eFbd6A49B35E8714C5f59D99De09A225b",
    "base": "0x4200000000000000000000000000000000000006",
    "arbitrum": "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
    "avalanche": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
    "bsc": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "fraxtal": "0xFC00000000000000000000000000000000000006",
    "xlayer": "0xe538905cf8410324e03a5a23c1c177a474d59b2b",  # WOKB
}


def main():
    txparams = {}
    network_name = network.show_active()
    if network_name == 'mainnet':
        network_name = 'ethereum'
    if network_name == 'ethereum':
        accounts.load('curve-deployer')
        txparams.update({'priority_fee': '2 gwei'})
    elif not network_name.endswith("-fork"):
        accounts.load('curve-deployer')
    txparams.update({'from': accounts[0]})

    stable_calc = INIT_DATA[network_name]["stable_calc"]
    crypto_calc = INIT_DATA[network_name]["crypto_calc"]
    if network_name == "ethereum":
        snx_coins = INIT_DATA[network_name]["snx_coins"]
        return Router.deploy(WETH[network_name], stable_calc, crypto_calc, snx_coins, txparams)
    if network_name == "optimism":
        snx_coins = INIT_DATA[network_name]["snx_coins"]
        return RouterOptimism.deploy(WETH[network_name], stable_calc, crypto_calc, snx_coins, txparams)
    if "tricrypto_meta_pools" in INIT_DATA[network_name]:
        tricrypto_meta_pools = INIT_DATA[network_name]["tricrypto_meta_pools"]
        return RouterSidechainTricryptoMeta.deploy(WETH[network_name], stable_calc, crypto_calc, tricrypto_meta_pools, txparams)
    else:
        return RouterSidechain.deploy(WETH[network_name], stable_calc, crypto_calc, txparams)
