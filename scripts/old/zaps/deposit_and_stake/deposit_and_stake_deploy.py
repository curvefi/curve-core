#!/usr/bin/python3

from brownie import network
from brownie import DepositAndStakeZap, accounts


def main():
    txparams = {}
    if network.show_active() == 'mainnet':
        accounts.load('curve-deployer')
        txparams.update({'priority_fee': '2 gwei'})
    elif not network.show_active().endswith("-fork"):
        accounts.load('curve-deployer')
    txparams.update({'from': accounts[0]})
    return DepositAndStakeZap.deploy(txparams)
