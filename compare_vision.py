from tools.screen import _grab_screen, _describe

png = _grab_screen()
if png is None:
    raise SystemExit("Could not capture the screen.")

with open("compare_screenshot.png", "wb") as f:
    f.write(png)  # so you can eyeball exactly what was captured

question = "Describe what is on the screen concisely and accurately."

print("=== llava ===")
print(_describe(png, question, "llava"))
print()
print("=== gemma3 ===")
print(_describe(png, question, "gemma3"))