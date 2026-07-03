
from ai_apps.api.proctor_api.rule_engine import safe_numeric

def test_safe_numeric():
    test_cases = [
        (10, 10),
        (3.14, 3.14),
        ("5", 5),
        ("123.456", 123.456),
        (None, None),
        ("not_a_number", None),
        ("", None),
    ]
    for input_val, expected in test_cases:
        result = safe_numeric(input_val)
        print(f"safe_numeric({input_val!r}) = {result!r}, expected {expected!r}")
        assert result == expected, f"Failed for {input_val!r}"

test_safe_numeric()
print("All tests passed!")

