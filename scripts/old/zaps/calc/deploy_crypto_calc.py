#!/usr/bin/python3

from brownie import network
from brownie import CryptoCalcZap, accounts

# STABLE_CALC_ZAP: constant(address) = 0xCA8d0747B5573D69653C3aC22242e6341C36e4b4
# MATH2: constant(address) = 0x69522fb5337663d3B4dFB0030b881c1A750Adb4f
# MATH3: constant(address) = 0x4f37A9d177470499A2dD084621020b023fcffc1F

ADDRESSES = {
    "bsc": {
        "stable_calc_zap": "0x0fE38dCC905eC14F6099a83Ac5C93BF2601300CF",
        "math2": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "math3": "0xEfadDdE5B43917CcC738AdE6962295A0B343f7CE",
    },
    "fraxtal": {
        "stable_calc_zap": "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4",
        "math2": "0xEfadDdE5B43917CcC738AdE6962295A0B343f7CE",
        "math3": "0xd6681e74eEA20d196c15038C580f721EF2aB6320",
    },
    "xlayer": {
        "stable_calc_zap": "0x0fE38dCC905eC14F6099a83Ac5C93BF2601300CF",
        "math2": "0xEfadDdE5B43917CcC738AdE6962295A0B343f7CE",
        "math3": "0xd6681e74eEA20d196c15038C580f721EF2aB6320",
    }
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

    addresses = ADDRESSES[network_name]
    txparams.update({'from': accounts[0]})
    return CryptoCalcZap.deploy(addresses["stable_calc_zap"], addresses["math2"], addresses["math3"], txparams)
