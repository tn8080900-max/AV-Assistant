import ast
import math
import operator


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def calculate(expression: str) -> str:
    if not expression or len(expression) > 200:
        raise ValueError("Enter a calculation under 200 characters.")

    try:
        tree = ast.parse(expression, mode="eval")
        result = _evaluate(tree.body)
    except (SyntaxError, ZeroDivisionError, OverflowError, TypeError) as exc:
        raise ValueError("That calculation is not valid.") from exc

    if not isinstance(result, (int, float)) or isinstance(result, bool):
        raise ValueError("That calculation did not produce a number.")
    if not math.isfinite(float(result)):
        raise ValueError("That calculation is outside the supported range.")
    if abs(result) > 1e100:
        raise ValueError("That result is outside the supported range.")
    return str(result)


def _evaluate(node: ast.expr) -> int | float:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        if abs(node.value) > 1e100:
            raise ValueError("Number is outside the supported range.")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponents are limited to 100.")
        return _BINARY_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate(node.operand))
    raise ValueError("Only basic arithmetic operators and numbers are allowed.")