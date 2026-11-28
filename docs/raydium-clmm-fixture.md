# Published Raydium CLMM candidate

The published Raydium example RAY/USDC pool
`61R1ndXxvsWXXkWSyNkCxnzwd3zUNB8Q2ibmkiLPC8ht` is kept as an
**untrusted fixture lead**, outside the execution-ready pool registry.
Source: https://github.com/raydium-io/raydium-docs-v1/blob/main/quick-start/deploy-clmm-pool.mdx

CI fetches the account from forked Solana RPC, decodes its owner and
pool state, checks both vaults, and inspects candidate tick arrays if
validation succeeds. The diagnostic reports UNVERIFIED for any missing,
unreadable or wrong-layout pool. Passing CI does NOT imply a third
executable venue; a signed swap_v2 simulation with balance accounting
will be required before that status changes.
