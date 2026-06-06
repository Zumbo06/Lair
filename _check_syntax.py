import ast, sys
try:
    with open("emulator_hub_app.py", encoding="utf-8") as f:
        ast.parse(f.read())
    print("Syntax OK")
    sys.exit(0)
except SyntaxError as e:
    print(f"Syntax Error: {e}")
    sys.exit(1)
