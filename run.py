import subprocess
import sys

SANDBOX_IMAGE = "react-agent-sandbox:latest"

def terminate_tree(process):
    if process.poll() is None:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

def ensure_sandbox_image():
    result = subprocess.run(
        ["docker", "image", "inspect", SANDBOX_IMAGE],
        capture_output=True,
    )

    if result.returncode != 0:
        subprocess.run(
            [
                "docker", "build",
                "-t", SANDBOX_IMAGE,
                "-f", "sandbox/Dockerfile",
                "sandbox",
            ],
            check=True,
        )

def main():
    subprocess.run(["docker", "compose", "up", "-d"])
    ensure_sandbox_image()
    frontend = subprocess.Popen(["npm.cmd", "run", "dev"], cwd="frontend")
    server   = subprocess.Popen([sys.executable, "-m", "uvicorn", "react_agent.api.server:app", "--reload"])

    try:
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        terminate_tree(frontend)
        terminate_tree(server)

        subprocess.run(["docker", "compose", "down"])

if __name__ == "__main__":
    main()