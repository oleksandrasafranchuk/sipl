from __future__ import annotations

from .. import ast as A
from . import terms as T

_ARITH = {"+": "add", "-": "sub", "*": "mult"}
_CMP = {"=": "eq", ">": "gr"}


def sem_P(program: A.Program):
    return sem_S(program.body)


def sem_S(s):
    if isinstance(s, A.Assign):
        return T.AS(s.var.name, sem_A(s.expr))
    if isinstance(s, A.Seq):
        return T.SeqT(sem_S(s.first), sem_S(s.second))
    if isinstance(s, A.If):
        return T.IFT(sem_B(s.cond), sem_S(s.then), sem_S(s.orelse))
    if isinstance(s, A.While):
        return T.WH(sem_B(s.cond), sem_S(s.body))
    if isinstance(s, A.Block):
        return sem_S(s.body)
    if isinstance(s, A.Skip):
        return T.Id()
    raise TypeError(s)


def sem_A(a):
    if isinstance(a, A.Num):
        return T.Const(a.value)
    if isinstance(a, A.Var):
        return T.Deref(a.name)
    if isinstance(a, A.BinA):
        return T.Sup(_ARITH[a.op], (sem_A(a.left), sem_A(a.right)))
    if isinstance(a, A.ParenA):
        return sem_A(a.inner)
    raise TypeError(a)


def sem_B(b):
    if isinstance(b, A.Cmp):
        return T.Sup(_CMP[b.op], (sem_A(b.left), sem_A(b.right)))
    if isinstance(b, A.Or):
        return T.Sup("or", (sem_B(b.left), sem_B(b.right)))
    if isinstance(b, A.Not):
        return T.Sup("neg", (sem_B(b.inner),))
    if isinstance(b, A.ParenB):
        return sem_B(b.inner)
    raise TypeError(b)
