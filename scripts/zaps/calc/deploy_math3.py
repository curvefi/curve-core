#!/usr/bin/python3

from brownie import network
from brownie import Math3, accounts


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
    return Math3.deploy(txparams)
