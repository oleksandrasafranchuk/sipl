pre:       Y > 0 or Y = 0
invariant: Y >= 0 and R * pow(X, Y) = pow(old(X), old(Y)) and X = old(X)
post:      R = pow(old(X), old(Y))
variant:   Y
bound:     1
domain:    X in -3..4; Y in 0..6; R in -2..3
