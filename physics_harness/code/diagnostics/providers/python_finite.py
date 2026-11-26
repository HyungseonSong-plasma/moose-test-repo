"""Finite, non-executing Python syntax interpretation (opt-in P3).

This is deliberately not a Python interpreter or a name-resolution proof.
Every result is a candidate under the declared lexical model. Unsupported
statements stop the affected path; unknown values never become exhaustive.
"""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from time import monotonic


class FiniteBudgetExceeded(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Alternatives:
    atoms: frozenset[tuple[str, str]] = frozenset()
    unknown: bool = True


UNKNOWN = Alternatives()
MAX_ALTERNATIVES = 8
MAX_STRING = 8192


def _value(atoms, unknown=False):
    atoms = frozenset(atoms)
    if len(atoms) > MAX_ALTERNATIVES:
        raise FiniteBudgetExceeded("PYTHON_STATIC_ALTERNATIVE_LIMIT")
    return Alternatives(atoms, unknown)


def _union(*values):
    return _value((a for v in values for a in v.atoms), any(v.unknown for v in values))


def _literal(node):
    if isinstance(node, ast.Constant):
        if type(node.value) is str and len(node.value) <= MAX_STRING:
            return _value((("str", node.value),))
        if type(node.value) is bool:
            return _value((("bool", "true" if node.value else "false"),))
    return UNKNOWN


def _concat(left, right):
    result = []
    unknown = left.unknown or right.unknown
    for lk, lv in left.atoms:
        for rk, rv in right.atoms:
            if lk != "str" or rk != "str" or len(lv) + len(rv) > MAX_STRING:
                unknown = True
            else:
                result.append(("str", lv + rv))
    return _value(result, unknown)


def _truth(value):
    if not value.unknown and value.atoms == frozenset((("bool", "true"),)):
        return True
    if not value.unknown and value.atoms == frozenset((("bool", "false"),)):
        return False
    return None


@dataclass(frozen=True, slots=True)
class FiniteResult:
    # AST objects are retained only within the existing collector invocation.
    calls: tuple[tuple[ast.Call, Alternatives], ...]
    returns: tuple[tuple[ast.FunctionDef, ast.Return, Alternatives], ...]
    unresolved: tuple[str, ...]


class _Bindings(ast.NodeVisitor):
    """Conservatively collect bindings in a single lexical scope."""
    def __init__(self):
        self.names = Counter()
        self.unsafe = False

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names[node.id] += 1

    def visit_Import(self, node):
        for item in node.names:
            self.names[item.asname or item.name.split(".")[0]] += 1

    def visit_ImportFrom(self, node):
        for item in node.names:
            if item.name == "*":
                self.unsafe = True
            self.names[item.asname or item.name] += 1

    def visit_FunctionDef(self, node):
        self.names[node.name] += 1

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_ExceptHandler(self, node):
        if node.name:
            self.names[node.name] += 1
        self.generic_visit(node)

    def visit_MatchAs(self, node):
        if node.name:
            self.names[node.name] += 1
        self.generic_visit(node)

    def visit_MatchStar(self, node):
        if node.name:
            self.names[node.name] += 1

    def visit_MatchMapping(self, node):
        if node.rest:
            self.names[node.rest] += 1
        self.generic_visit(node)

    def visit_Global(self, node):
        self.unsafe = True

    visit_Nonlocal = visit_Global


def analyze_finite_python(root: ast.Module, *, max_seconds: float) -> FiniteResult:
    """Compute finite lexical candidates, without importing/eval/exec.

    Explicitly bounded to top-level ordinary functions, simple local
    assignments, returns, if/else, conditional expressions, literal string
    operations, and inline string-key dictionaries. Arbitrary calls are
    unknown values; their side effects, globals and external rebinding
    are outside the model. Unsupported control flow stops the path.
    """
    started = monotonic()
    nodes = []
    for node in ast.walk(root):
        nodes.append(node)
        if len(nodes) > 6000 or monotonic() - started > max_seconds:
            raise FiniteBudgetExceeded("PYTHON_STATIC_AST_BUDGET")
    module = _Bindings()
    module.visit(root)
    unstable = {name for node in nodes if isinstance(node, ast.Global) for name in node.names}
    globals_ = {}
    eligible = []
    for stmt in root.body:
        if (isinstance(stmt, ast.FunctionDef) and not stmt.decorator_list
                and module.names[stmt.name] == 1):
            eligible.append(stmt)
            if stmt.name not in unstable and not module.unsafe:
                globals_[stmt.name] = _value((("fn", stmt.name),))
        elif (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
              and isinstance(stmt.targets[0], ast.Name)):
            name = stmt.targets[0].id
            if module.names[name] == 1 and name not in unstable and not module.unsafe:
                globals_[name] = _literal(stmt.value)
    if len(eligible) > 64:
        raise FiniteBudgetExceeded("PYTHON_STATIC_FUNCTION_BUDGET")
    calls = {}
    returns = {}
    unresolved = {"PYTHON_STATIC_LEXICAL_MODEL_NOT_GLOBAL_CLOSURE"}
    steps = 0

    def tick(depth):
        nonlocal steps
        steps += 1
        if steps > 4096 or depth > 32 or monotonic() - started > max_seconds:
            raise FiniteBudgetExceeded("PYTHON_STATIC_INTERPRETATION_BUDGET")

    def record(mapping, key, value):
        mapping[key] = _union(mapping[key], value) if key in mapping else value

    def expression(node, env, depth):
        tick(depth)
        if node is None:
            return UNKNOWN
        if isinstance(node, ast.Constant):
            return _literal(node)
        if isinstance(node, ast.Name):
            return env.get(node.id, globals_.get(node.id, UNKNOWN))
        if isinstance(node, ast.IfExp):
            test = _truth(expression(node.test, env, depth + 1))
            if test is True:
                return expression(node.body, env, depth + 1)
            if test is False:
                return expression(node.orelse, env, depth + 1)
            return _union(expression(node.body, env, depth + 1),
                          expression(node.orelse, env, depth + 1))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return _concat(expression(node.left, env, depth + 1),
                           expression(node.right, env, depth + 1))
        if isinstance(node, ast.JoinedStr):
            value = _value((("str", ""),))
            for part in node.values:
                if isinstance(part, ast.Constant):
                    fragment = _literal(part)
                elif isinstance(part, ast.FormattedValue) and part.conversion == -1 and part.format_spec is None:
                    fragment = expression(part.value, env, depth + 1)
                else:
                    fragment = UNKNOWN
                value = _concat(value, fragment)
            return value
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Dict):
            table = {}
            for key, val in zip(node.value.keys, node.value.values):
                if not isinstance(key, ast.Constant) or type(key.value) is not str or key.value in table:
                    return UNKNOWN
                table[key.value] = expression(val, env, depth + 1)
            if len(table) > MAX_ALTERNATIVES:
                raise FiniteBudgetExceeded("PYTHON_STATIC_ALTERNATIVE_LIMIT")
            index = expression(node.slice, env, depth + 1)
            values = [table.get(v, UNKNOWN) if k == "str" else UNKNOWN for k, v in index.atoms]
            if index.unknown:
                values.extend(table.values())
                values.append(UNKNOWN)
            return _union(*values) if values else UNKNOWN
        if isinstance(node, ast.Call):
            callee = expression(node.func, env, depth + 1)
            # Do not infer the output of an arbitrary call, even if its
            # syntactic callee is known. The call itself is a candidate.
            record(calls, node, callee)
            for arg in node.args:
                expression(arg, env, depth + 1)
            for kw in node.keywords:
                expression(kw.value, env, depth + 1)
            return UNKNOWN
        return UNKNOWN

    def suite(statements, env, function, depth):
        tick(depth)
        for stmt in statements:
            tick(depth)
            if isinstance(stmt, ast.Assign) and all(isinstance(t, ast.Name) for t in stmt.targets):
                value = expression(stmt.value, env, depth + 1)
                for target in stmt.targets:
                    env[target.id] = value
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                env[stmt.target.id] = expression(stmt.value, env, depth + 1)
            elif isinstance(stmt, ast.Expr):
                expression(stmt.value, env, depth + 1)
            elif isinstance(stmt, ast.Pass):
                continue
            elif isinstance(stmt, ast.Return):
                record(returns, (function, stmt), expression(stmt.value, env, depth + 1))
                return None
            elif isinstance(stmt, ast.If):
                test = _truth(expression(stmt.test, env, depth + 1))
                branches = []
                if test is not False:
                    branches.append(suite(stmt.body, dict(env), function, depth + 1))
                if test is not True:
                    branches.append(suite(stmt.orelse, dict(env), function, depth + 1))
                live = [branch for branch in branches if branch is not None]
                if not live:
                    return None
                names = set().union(*(branch.keys() for branch in live))
                env = {name: _union(*(branch.get(name, UNKNOWN) for branch in live))
                       for name in sorted(names)}
            else:
                unresolved.add(f"PYTHON_STATIC_UNSUPPORTED_STATEMENT:{stmt.lineno}")
                # Stop this path rather than speculate about its writes.
                return None
        return env

    for function in eligible:
        bindings = _Bindings()
        for stmt in function.body:
            bindings.visit(stmt)
        nested = [item for stmt in function.body for item in ast.walk(stmt)]
        if bindings.unsafe or any(isinstance(n, (
            ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
            ast.NamedExpr, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
            ast.Yield, ast.YieldFrom, ast.Await,
        )) for n in nested):
            unresolved.add(f"PYTHON_STATIC_UNSUPPORTED_SCOPE:{function.lineno}")
            continue
        args = function.args
        names = set(bindings.names) | {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
        if args.vararg:
            names.add(args.vararg.arg)
        if args.kwarg:
            names.add(args.kwarg.arg)
        # Defaults are not assumed: callers can supply any argument value.
        suite(function.body, {name: UNKNOWN for name in names}, function, 0)

    def position(node):
        return node.lineno, node.col_offset, node.end_lineno, node.end_col_offset

    return FiniteResult(
        tuple(sorted(calls.items(), key=lambda item: position(item[0]))),
        tuple((fn, ret, value) for (fn, ret), value in sorted(
            returns.items(), key=lambda item: position(item[0][1]))),
        tuple(sorted(unresolved)),
    )
