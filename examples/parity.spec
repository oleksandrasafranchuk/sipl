pre:       N >= 0
invariant: K >= 0 and (E = 1 or E = 0) and (E = 1 -> even(N - K)) and (E = 0 -> odd(N - K)) and N = old(N)
post:      (E = 1 and even(old(N))) or (E = 0 and odd(old(N)))
variant:   K
bound:     1
domain:    N in 0..12; K in 0..12; E in 0..1
