import subprocess
import json

# ── Tools ──────────────────────────────────────────────────────────────────────

def check_ec2_state(instance_name: str, region: str = "us-east-1", cred_file: str = "") -> str:
    """Check EC2 instance state using AWS.Tools.EC2 PowerShell module."""
    import tempfile, os

    cred_file = cred_file or f"{os.environ.get('USERPROFILE', '')}\\Downloads\\credentials-GCCS"

    ps_content = f"""
$CredFile = "{cred_file}"
if ($CredFile -and (Test-Path $CredFile)) {{
    $creds = Get-Content $CredFile
    $Env:AWS_ACCESS_KEY_ID     = ($creds | Where-Object {{ $_ -match "^aws_access_key_id" }})     -split " = " | Select-Object -Last 1 | ForEach-Object {{ $_.Trim() }}
    $Env:AWS_SECRET_ACCESS_KEY = ($creds | Where-Object {{ $_ -match "^aws_secret_access_key" }}) -split " = " | Select-Object -Last 1 | ForEach-Object {{ $_.Trim() }}
    $Env:AWS_SESSION_TOKEN     = ($creds | Where-Object {{ $_ -match "^aws_session_token" }})     -split " = " | Select-Object -Last 1 | ForEach-Object {{ $_.Trim() }}
}}
try {{
    Import-Module AWS.Tools.EC2 -ErrorAction Stop
}} catch {{
    Write-Output "MODULE_ERROR: AWS.Tools.EC2 not found. Run: Install-Module AWS.Tools.EC2"
    exit 1
}}
try {{
    $instances = Get-EC2Instance -Region "{region}" | Select-Object -ExpandProperty Instances
    $pattern = "{instance_name}".ToLower()
    $found = @()
    foreach ($i in $instances) {{
        $name = ($i.Tags | Where-Object {{ $_.Key -eq 'Name' }}).Value
        if ($name -and $name.ToLower() -like "*$($pattern.Replace('*',''))*") {{
            $found += "$name | $($i.State.Name) | $($i.InstanceType) | $($i.PrivateIpAddress)"
        }}
    }}
    if ($found.Count -eq 0) {{ Write-Output "NO_MATCHES" }}
    else {{ $found | ForEach-Object {{ Write-Output $_ }} }}
}} catch {{
    Write-Output "AWS_ERROR: $_"
}}
"""
    tmp = tempfile.NamedTemporaryFile(suffix=".ps1", delete=False, mode="w", encoding="utf-8")
    tmp.write(ps_content)
    tmp.close()

    try:
        result = subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", tmp.name],
            capture_output=True, text=True, timeout=60
        )
        output = result.stdout.strip()
        if "MODULE_ERROR:" in output:
            return output
        if "AWS_ERROR:" in output:
            return f"AWS error: {output}"
        if output == "NO_MATCHES":
            return f"No instances found matching '{instance_name}'"
        return output if output else result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "Timed out."
    except Exception as e:
        return f"Error: {e}"
    finally:
        import os
        os.unlink(tmp.name)


# ── MR Prep ───────────────────────────────────────────────────────────────────

def mr_prep(servers_input: str) -> str:
    """Generate MR deployment prep output from a list of ADM or APP server names."""
    servers = [s.strip() for s in servers_input.replace(",", "\n").splitlines() if s.strip()]

    pairs = []
    for s in servers:
        upper = s.upper()
        if "WADM" in upper:
            web = upper.replace("WADM", "WEB")
        elif "APP" in upper:
            web = upper.replace("APP", "WEB")
        else:
            web = upper
        pairs.append((upper, web))

    cb_srvrlst = ",".join(f"{s},{w}" for s, w in pairs)
    report_servers = "\n".join(s for s, _ in pairs)

    return (
        "#### 30mins before ####\n"
        "Run winrmfix\n"
        "Run web monitor\n"
        "Smoketest\n"
        "Run End\n"
        "\n\n"
        f"CB Srvrlst\t:\n{cb_srvrlst}\n"
        "\n\n"
        "REPORT\n"
        "Successfully applied to below assigned servers.\n"
        f"\n{report_servers}\n"
        "\n\n"
        "Enable Login:\n\n"
        "Tools Used:\n\n"
        "Errors/Issues encountered:"
    )


# ── Claude bridge ──────────────────────────────────────────────────────────────

def ask_claude(prompt: str, history: list = None) -> str:
    """Call Claude with optional conversation history for context."""
    if history:
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in history[-6:]  # last 3 exchanges
        )
        full_prompt = f"Conversation so far:\n{history_text}\n\nUser: {prompt}"
    else:
        full_prompt = prompt

    result = subprocess.run(
        ["claude", "-p", full_prompt, "--output-format", "json"],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    return data.get("result", "")


def route_and_respond(user_input: str, history: list) -> str:
    """Ask Claude what to do, then execute if it needs a tool."""

    classify_prompt = f"""You are a release engineering assistant with access to two tools:
1. check_ec2_state — check EC2 instance status
2. mr_prep — generate MR deployment prep output from server names

Conversation history (for context):
{chr(10).join(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in history[-4:])}

User just said: "{user_input}"

If the user wants EC2 instance state/status, reply with EXACTLY this format (no extra text):
TOOL: check_ec2_state
instance_name: <pattern>
region: <region or us-east-1>

If the user wants MR prep output (server list, deployment prep, CB Srvrlst), reply with EXACTLY this format (no extra text):
TOOL: mr_prep
servers: <comma or newline separated server names>

Otherwise, just answer the question directly as a helpful assistant."""

    response = ask_claude(classify_prompt)

    if response.strip().startswith("TOOL: mr_prep"):
        lines = response.strip().splitlines()
        params = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                params[k.strip()] = v.strip()
        servers = params.get("servers", "")
        print(f"\n[Tool] Generating MR prep for: {servers[:60]}...")
        return mr_prep(servers)

    if response.strip().startswith("TOOL: check_ec2_state"):
        lines = response.strip().splitlines()
        params = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                params[k.strip()] = v.strip()

        instance_name = params.get("instance_name", "")
        region = params.get("region", "us-east-1")

        print(f"\n[Tool] Checking EC2: {instance_name} in {region}...")
        result = check_ec2_state(instance_name, region)

        followup = f"""The user asked: "{user_input}"

EC2 query result:
{result}

Summarize this clearly for the user."""
        return ask_claude(followup)

    return response


# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    print("Release Assistant - type 'exit' to quit\n")
    history = []

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye.")
            break
        if not user_input:
            continue

        response = route_and_respond(user_input, history)

        # Save to history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})

        print(f"\nAssistant: {response}\n")

if __name__ == "__main__":
    main()
