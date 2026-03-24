import subprocess
import json

def ask_claude(prompt):
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True,
        text=True
    )
    data = json.loads(result.stdout)
    return data.get("result", "")

response = ask_claude("Say hello in one sentence.")
print(response)
