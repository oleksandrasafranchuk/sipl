pre:       X >= 0
invariant: X >= 0 and P * pow(3, X) = pow(3, old(X))
post:      P = pow(3, old(X))
variant:   X
bound:     1
domain:    X in 0..8; P in 0..30
