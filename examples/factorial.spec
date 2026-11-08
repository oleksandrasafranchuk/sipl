pre:       N >= 0
invariant: F = fact(K) and K <= N and N = old(N)
post:      F = fact(old(N))
variant:   N - K
bound:     1
domain:    N in 0..7; K in 0..7; F in 0..6
