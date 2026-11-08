pre:       X >= 0 and Y > 0
invariant: X = Q * Y + R and R >= 0 and Y > 0 and X = old(X) and Y = old(Y)
post:      Q = div(old(X), old(Y)) and R = mod(old(X), old(Y))
variant:   R
bound:     0
domain:    X in 0..15; Y in 1..5; Q in 0..4; R in 0..15
