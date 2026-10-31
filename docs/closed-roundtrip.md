# Closed two-leg swap simulations

A **closed** WSOL → USDC → WSOL route uses *exact-output* for the first
leg (buy a fixed USDC base-unit amount, subject to a maximum WSOL
spend), then *exact-input* for the second leg using that same USDC
amount. As both instructions run atomically, their successful execution
must leave zero USDC balance. The simulated final WSOL token balance
minus starting WSOL funding and estimated network fee is a direct
WSOL-denominated net result.

The simulation rejects residual USDC, missing transaction fee, and
failed swaps as proof of executable net profitability. It does not
guarantee mainnet fill, execution on another slot, or cross-DEX
arbitrage. The controlled test deliberately traverses the same
Whirlpool twice; a profitable path would need distinct venue pricing
and net-profit guardrails enforced by the program/transaction.
