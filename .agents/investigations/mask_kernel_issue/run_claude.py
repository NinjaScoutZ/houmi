import subprocess
import os

cwd = r"e:\houmi\.agents\investigations\mask_kernel_issue"

command = 'claude -p "Please read and analyze QUESTION.md in the current directory and provide a comprehensive solution and engineering plan for all 4 consultation questions." < NUL'

print("Running command:", command)
result = subprocess.run(command, capture_output=True, text=True, cwd=cwd, shell=True)

print("Return code:", result.returncode)
if result.stdout:
    response_path = os.path.join(cwd, "CLAUDE_RESPONSE.md")
    with open(response_path, "w", encoding="utf-8") as out:
        out.write(result.stdout)
    print("Response written to", response_path)
    print("Preview:\n", result.stdout[:800])
else:
    print("No stdout. Stderr:", result.stderr)
