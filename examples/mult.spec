pre:       Y >= 0
invariant: Z + K * X = old(X) * old(Y) and K >= 0 and X = old(X)
post:      Z = old(X) * old(Y)
variant:   K
bound:     1
domain:    X in -4..5; Y in 0..6; Z in -3..3; K in 0..6
