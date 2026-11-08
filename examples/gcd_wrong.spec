pre:       true
invariant: gcd(M, N) = gcd(old(M), old(N))
post:      M = gcd(old(M), old(N))
variant:   M + N
bound:     2
domain:    M, N in -2..6
