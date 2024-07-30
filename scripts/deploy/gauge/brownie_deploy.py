from brownie import ZERO_ADDRESS, ChildGauge, ChildGaugeFactory, OptimismBridger, RootGauge, RootGaugeFactory, accounts

# DEPLOYER = accounts.load("xchain_deployer", password="")
txparams = {"from": DEPLOYER, "priority_fee": "1 gwei", "max_fee": "20 gwei"}

CRV = "0xD533a949740bb3306d119CC777fa900bA034cd52"
GAUGE_CONTROLLER = "0x2F50D538606Fa9EDD2B11E2446BEb18C9D5846bB"
MINTER = "0xd061D61a4d941c39E5453435B6345Dc261C2fcE0"
VE = "0x5f3b5DfEb7B28CDbD7FAba78963EE202a494e2A2"

ANYCALL = ZERO_ADDRESS

# TODO
L2_CRV20 = "0x1E4F97b9f9F913c46F1632781732927B9019C68b"
# L1_BRIDGE = "0x95fC37A27a2f68e3A647CDc081F0A89bb47c3012"
txparams = {"from": DEPLOYER, "gas_price": "150 gwei"}


def deploy_root():
    # 0xeF672bD94913CB6f1d2812a6e18c1fFdEd8eFf5c
    factory = RootGaugeFactory.at("0xeF672bD94913CB6f1d2812a6e18c1fFdEd8eFf5c")  # deploy(ANYCALL, DEPLOYER, txparams)
    # 0x10Ac65a9F710C3d607D213784e5b8632c77D5d4f
    gauge_impl = RootGauge.at(
        "0x10Ac65a9F710C3d607D213784e5b8632c77D5d4f"
    )  # deploy(CRV, GAUGE_CONTROLLER, MINTER, txparams)
    # RootOracle.deploy(factory, VE, ANYCALL, {"from": DEPLOYER})

    # set implementation
    # factory.set_implementation(gauge_impl, txparams)

    # bridger = OptimismBridger.deploy(L2_CRV20, L1_BRIDGE, txparams)
    # factory.set_child(5000, bridger, txparams)


def deploy_child(crv_addr=L2_CRV20):
    # 0xeF672bD94913CB6f1d2812a6e18c1fFdEd8eFf5c
    factory = ChildGaugeFactory.deploy(ANYCALL, crv_addr, DEPLOYER, txparams)
    # 0x10Ac65a9F710C3d607D213784e5b8632c77D5d4f
    gauge_impl = ChildGauge.deploy(crv_addr, factory, txparams)
    # ChildOracle.deploy(ANYCALL, {"from": DEPLOYER})

    # set implementation
    factory.set_implementation(gauge_impl, txparams)
