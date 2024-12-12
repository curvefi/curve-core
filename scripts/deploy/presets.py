from pydantic import BaseModel


class CryptoPoolPresets(BaseModel):
    A: int = 20000000
    gamma: int = 1000000000000000
    mid_fee: int = 5000000
    out_fee: int = 45000000
    fee_gamma: int = 5000000000000000
    allowed_extra_profit: int = 10000000000
    adjustment_step: int = 5500000000000
    ma_exp_time: int = 866
    initial_price: int = 10**18
