"""Canonical market identifiers for SSE/SZSE/BSE.

Current BSE securities use Tencent bj<code> and Eastmoney market id 0.
SSE securities use sh<code> / Eastmoney market id 1; SZSE uses sz<code> / 0.
"""

def tencent_symbol(code: str, index_000300: bool = False) -> str:
    code = str(code)
    if code.startswith(("8", "9")):
        return "bj" + code
    if (index_000300 and code == "000300") or code.startswith(("5", "6")):
        return "sh" + code
    return "sz" + code


def eastmoney_secid(code: str, index_000300: bool = False) -> str:
    code = str(code)
    market = "1." if ((index_000300 and code == "000300") or code.startswith(("5", "6"))) else "0."
    return market + code
