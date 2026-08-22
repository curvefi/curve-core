# pragma version 0.3.10
# pragma optimize gas

"""
@title CurveStableSwapMath
@custom:version 1.0.0
@author Curve.Fi
@license Copyright (c) Curve.Fi, 2020-2024 - all rights reserved
@notice Core math functions for StableSwapMetaNG implementation, including D invariant and get_y calculations.
"""

# ------------------------------- Constants ---------------------------------

version: public(constant(String[8])) = "1.0.0"

# Maximum number of coins supported in the pool.
MAX_COINS: constant(uint256) = 8
MAX_COINS_128: constant(int128) = 8
# A_PRECISION is a scaling factor for the amplification parameter 'A' (e.g., A * 100).
A_PRECISION: constant(uint256) = 100


# ------------------------------- Functions ---------------------------------

@external
@pure
def get_y(
    i: int128,
    j: int128,
    x: uint256,
    xp: DynArray[uint256, MAX_COINS],
    _amp: uint256,
    _D: uint256,
    _n_coins: uint256
) -> uint256:
    """
    Calculate the amount of coin x[j] (y) that is received if coin x[i] 
    is set to 'x' (new reserve for coin i) while maintaining the invariant D.

    Solves the quadratic equation iteratively (Newton's method).
    x_j**2 + x_j * (sum' - (A*n**n - 1) * D / (A * n**n)) = D ** (n + 1) / (n ** (2 * n) * prod' * A)
    """

    n_coins_128: int128 = convert(_n_coins, int128)

    # Input validation
    assert i != j, "dev: same coin"
    assert j >= 0 and j < n_coins_128, "dev: invalid j index"
    assert i >= 0 and i < n_coins_128, "dev: invalid i index"

    amp: uint256 = _amp
    D: uint256 = _D
    
    S_: uint256 = 0 # Sum of reserves excluding the two coins i and j
    c: uint256 = D   # Product calculation part (numerator for c)
    Ann: uint256 = amp * _n_coins
    
    # Calculate S_ (sum excluding x_i and x_j) and the product part (c)
    for _idx in range(MAX_COINS_128):

        if _idx == n_coins_128:
            break

        _x: uint256 = 0
        if _idx == i:
            _x = x
        elif _idx != j:
            _x = xp[_idx]
        else:
            continue

        S_ += _x
        c = c * D / (unsafe_mul(_x, _n_coins)) # Using unsafe_mul for gas optimization
    
    # Finalize c and b calculations for the quadratic equation x^2 + b*x = c
    c = c * D * A_PRECISION / (unsafe_mul(Ann, _n_coins))
    # b = S_ + D * A_PRECISION / Ann - D
    b: uint256 = unsafe_add(S_, unsafe_div(unsafe_mul(D, A_PRECISION), Ann)) 

    y: uint256 = D
    y_prev: uint256 = 0

    # Iterative solution (Newton's method)
    # y[k+1] = (y[k]*y[k] + c) / (2 * y[k] + b - D)
    for _i in range(255):
        y_prev = y
        y = unsafe_div(unsafe_add(unsafe_mul(y, y), c), unsafe_sub(unsafe_add(unsafe_mul(2, y), b), D))
        
        # Check for convergence (within a precision of 1)
        if y > y_prev:
            if unsafe_sub(y, y_prev) <= 1:
                return y
        else:
            if unsafe_sub(y_prev, y) <= 1:
                return y
    
    # Should be unreachable under normal circumstances
    raise # dev: calculation failed to converge


@external
@pure
def get_D(
    _xp: DynArray[uint256, MAX_COINS],
    _amp: uint256,
    _n_coins: uint256
) -> uint256:
    """
    Calculate the D invariant iteratively (Newton's method).
    
    A * sum(x_i) * n**n + D = A * D * n**n + D**(n+1) / (n**n * prod(x_i))
    """
    
    S: uint256 = 0 # Sum of all coin reserves
    for x in _xp:
        S += x
    if S == 0:
        return 0 # Handle empty pool case

    D: uint256 = S
    Ann: uint256 = unsafe_mul(_amp, _n_coins) # A * n
    
    n_power_n: uint256 = pow_mod256(_n_coins, _n_coins)

    Dprev: uint256 = 0
    
    # Iterative solution (Newton's method)
    for i in range(255):
        
        D_P: uint256 = D # D_P = D**(n+1) / (n**n * prod(x_i)) * n
        for x in _xp:
            D_P = unsafe_div(unsafe_mul(D_P, D), x) 
        
        D_P = unsafe_div(D_P, n_power_n)
        Dprev = D

        # D[j+1] = (A * n**n * S + D_P * n) * D / ((A * n**n - 1) * D + (n + 1) * D_P)
        # Using A_PRECISION=100 as the scaling factor for A
        D = unsafe_div(
            unsafe_mul(
                unsafe_add(unsafe_div(unsafe_mul(Ann, S), A_PRECISION), unsafe_mul(D_P, _n_coins)),
                D
            ),
            unsafe_add(
                unsafe_div(unsafe_mul(unsafe_sub(Ann, A_PRECISION), D), A_PRECISION),
                unsafe_mul(unsafe_add(_n_coins, 1), D_P)
            )
        )
        
        # Check for convergence (within a precision of 1)
        if D > Dprev:
            if unsafe_sub(D, Dprev) <= 1:
                return D
        else:
            if unsafe_sub(Dprev, D) <= 1:
                return D
                
    raise # dev: calculation failed to converge


@external
@pure
def get_y_D(
    A: uint256,
    i: int128,
    xp: DynArray[uint256, MAX_COINS],
    D: uint256,
    _n_coins: uint256
) -> uint256:
    """
    Calculate x[i] (y) required to meet the invariant D, given the other coin reserves xp,
    used primarily for calculating the required withdrawal amount in 'remove_liquidity'.

    This function shares logic with get_y but solves for a specific coin index 'i' 
    given a target invariant 'D'.
    """
    n_coins_128: int128 = convert(_n_coins, int128)

    # Input validation
    assert i >= 0 and i < n_coins_128, "dev: invalid i index"

    S_: uint256 = 0
    c: uint256 = D
    Ann: uint256 = unsafe_mul(A, _n_coins)

    # Calculate S_ (sum excluding x_i) and the product part (c)
    for _idx in range(MAX_COINS_128):

        if _idx == n_coins_128:
            break

        if _idx != i:
            _x: uint256 = xp[_idx]
        else:
            continue
            
        S_ += _x
        c = c * D / (unsafe_mul(_x, _n_coins))

    # Finalize c and b calculations
    c = c * D * A_PRECISION / (unsafe_mul(Ann, _n_coins))
    b: uint256 = unsafe_add(S_, unsafe_div(unsafe_mul(D, A_PRECISION), Ann))
    
    y: uint256 = D
    y_prev: uint256 = 0

    # Iterative solution (Newton's method)
    for _i in range(255):
        y_prev = y
        y = unsafe_div(unsafe_add(unsafe_mul(y, y), c), unsafe_sub(unsafe_add(unsafe_mul(2, y), b), D))
        
        # Check for convergence (within a precision of 1)
        if y > y_prev:
            if unsafe_sub(y, y_prev) <= 1:
                return y
        else:
            if unsafe_sub(y_prev, y) <= 1:
                return y
                
    raise # dev: calculation failed to converge


@external
@pure
def exp(x: int256) -> uint256:

    """
    @dev Calculates the natural exponential function of a signed integer (e^x) with
          a precision of 1e18 (WAD). 
    @notice This highly optimized function is derived from the Snekmate library.
    @param x The input signed integer value (fixed point 1e18).
    @return uint256 The calculation result (fixed point 1e18).
    """
    
    # NOTE: The 'empty(uint256)' return is retained for compliance with the original
    # highly optimized Vyper math library pattern (often reverting if used incorrectly).
    
    # 1. Input range check for results < 0.5 (underflow)
    if (x <= -41446531673892822313):
        return empty(uint256)

    # 2. Input range check for results > (2**255 - 1) / 1e18 (overflow)
    # The max safe input is slightly less than 135.306 * 1e18
    assert x < 135305999368893231589, "wad_exp overflow"

    value: int256 = x

    # 3. Base Conversion: 1e18 -> 2**96 (High precision binary base)
    value = unsafe_div(value << 78, 5 ** 18)

    # 4. Range Reduction: x = x' + k * log(2), where x' is in a small range
    k: int256 = unsafe_add(unsafe_div(value << 96, 54916777467707473351141471128), 2 ** 95) >> 96
    value = unsafe_sub(value, unsafe_mul(k, 54916777467707473351141471128))

    # 5. Rational Approximation: Evaluate exp(x') using polynomial approximation
    y: int256 = unsafe_add(unsafe_mul(unsafe_add(value, 1346386616545796478920950773328), value) >> 96, 57155421227552351082224309758442)
    p: int256 = unsafe_add(unsafe_mul(unsafe_add(unsafe_mul(unsafe_sub(unsafe_add(y, value), 94201549194550492254356042504812), y) >> 96, 28719021644029726153956944680412240), value), 4385272521454847904659076985693276 << 96)

    q: int256 = unsafe_add(unsafe_mul(unsafe_sub(value, 2855989394907223263936484059900), value) >> 96, 50020603652535783019961831881945)
    q = unsafe_sub(unsafe_mul(q, value) >> 96, 533845033583426703283633433725380)
    q = unsafe_add(unsafe_mul(q, value) >> 96, 3604857256930695427073651918091429)
    q = unsafe_sub(unsafe_mul(q, value) >> 96, 14423608567350463180887372962807573)
    q = unsafe_add(unsafe_mul(q, value) >> 96, 26449188498355588339934803723976023)

    r: int256 = unsafe_div(p, q)

    # 6. Final scaling and base conversion: 2**96 -> 1e18 (WAD)
    # The final step is calculated in 2**213 base to ensure positive results after the final shift.
    # Conversion from signed r (int256) to unsigned uint256 is done using bytes32 casting.
    return unsafe_mul(convert(convert(r, bytes32), uint256), 3822833074963236453042738258902158003155416615667) >> convert(unsafe_sub(195, k), uint256)
