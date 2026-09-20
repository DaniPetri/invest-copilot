"""German number formatting for text that reaches users (1.234,56 / 0,15 %)."""


def de_num(x: float, decimals: int = 0) -> str:
    """German number format: 1.234,56"""
    s = f"{abs(x):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-{s}" if x < 0 and round(x, decimals) != 0 else s


def de_pct(fraction: float, decimals: int = 2) -> str:
    """A fraction as a percentage: 0.0015 -> '0,15 %'"""
    return f"{de_num(fraction * 100, decimals)} %"
