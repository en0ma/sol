# First fork-verified CLMM swap

On 2026-10-14, Surfpool CI #210 successfully simulated an atomic
Raydium CPMM WSOL->USDC exact-output swap followed by a Raydium CLMM
USDC->RAY exact-input swap using a **locally provisioned address lookup
table** and a signed Solana v0 transaction.

Observed results: serialized 1,026 bytes; compute 68,397 units;
initial 1,000,000 WSOL lamports, final 904,041 WSOL lamports;
intermediate USDC residual 0; RAY received 5,427 base units.
Both programs returned success in one `simulateTransaction` call.
The local ALT setup uses `sendTransaction` exclusively to localhost
Surfpool; the swap transaction itself was never broadcast.

The swap gate is now mandatory in mainnet-fork CI. This is a *two-hop,
open-ended conversion*, NOT a closed or net-profitable arbitrage cycle,
and does not imply that arbitrary CLMM pools/routes are safe to execute.
CLMM is not added to unrestricted executable-route selection.
