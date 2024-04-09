import torch

import tensorgrad.tensor as tg
import tensorgrad.functions as F


def rand_values(variables, **shape):
    return {v: torch.randn([shape[e] for e in v.edges], names=v.edges) for v in variables}


def assert_close(a, b):
    assert set(a.names) == set(b.names)
    a = a.align_to(*b.names)
    torch.testing.assert_close(a.rename(None), b.rename(None))


def test_simple_grad():
    x = tg.Variable("x", ["x"])
    A = tg.Variable("A", ["x", "y"])
    ts = rand_values([x, A], x=2, y=3)
    res = (A @ x).grad(x).simplify()
    assert_close(res.evaluate(ts), ts[A].rename("x_", "y"))


def test_simple_hessian():
    x = tg.Variable("x", ["x"])
    A = tg.Variable("A", ["x", "y"])
    ts = rand_values([x, A], x=2, y=2)
    quad = x @ A @ x.rename({"x": "y"})
    res = quad.grad(x).grad(x).simplify()
    assert_close(res.evaluate(ts), 2 * ts[A].rename("x_", "x__"))

    x = tg.Variable("x", ["x"])
    y = tg.Variable("y", ["y"])
    A = tg.Variable("A", ["x", "y"])
    ts = rand_values([x, y, A], x=2, y=3)
    frob = F.frobenius2(A @ x - y)
    hess = frob.grad(x).grad(x).simplify().evaluate(ts)
    # Hessian of ||Ax - y||^2 is 2 * A^T A
    expected = 2 * ts[A].rename("x_", "y") @ ts[A].align_to("y", "x").rename("y", "x__")
    assert_close(hess, expected)


def test_derivative_of_hadamard_product():
    a = tg.Variable("a", ["i", "j"])
    b = tg.Variable("b", ["i", "j"])
    ts = rand_values([a, b], i=2, j=3)

    print((a * b).grad(a).simplify())

    torch.testing.assert_close((a * b).grad(a).simplify().evaluate(ts).sum(), ts[b].sum())
    torch.testing.assert_close((a * b).grad(b).simplify().evaluate(ts).sum(), ts[a].sum())


def test_f_0_0():
    x = tg.Variable("x", [])
    f = F.Function("f", [], (x,))
    expr = f.grad(x).simplify()
    assert set(expr.edges) == set()
    assert expr == tg.Function("D_0f", [], (x,))


def test_f_0_1():
    x = tg.Variable("x", ["i"])
    f = F.Function("f", [], (x, "i"))
    expr = f.grad(x).simplify()
    assert set(expr.edges) == {"i_"}
    fg = F.Function("D_0f", ["i_"], (x, "i"))
    assert expr == fg


def test_f_0_2():
    x = tg.Variable("x", ["b", "i"])
    f = F.Function("f", [], (x, "i"))
    expr = f.grad(x).simplify()
    assert set(expr.edges) == {"b", "b_", "i_"}
    x_renamed = x.rename({"b": "b_"})
    fg = F.Function("D_0f", ["i_"], (x_renamed, "i")) @ tg.Copy(["b", "b_", "b__"])
    assert expr == fg


def test_f_1_0():
    x = tg.Variable("x", [])
    f = F.Function("f", ["y"], (x,))
    expr = f.grad(x).simplify()
    assert set(expr.edges) == {"y"}
    assert expr == tg.Function("D_0f", ["y"], (x,))


def test_f_1_1():
    x = tg.Variable("x", ["i"])
    f = F.Function("f", ["y"], (x, "i"))
    expr = f.grad(x).simplify()
    assert set(expr.edges) == {"y", "i_"}
    assert expr == tg.Function("D_0f", ["y"], (x,))
