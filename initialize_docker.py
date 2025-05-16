import subprocess
import time
import sys
import re  # For parsing ollama list output

OLLAMA_IMAGE = "ollama/ollama"
DEFAULT_MODEL_NAME = "gemma3:4b"  # Renamed from MODEL_NAME to be more specific

# Configuration for the Ollama containers
CONTAINERS_CONFIG = [
    {
        "name": "ollama",
        "port": "3001",
        "host_port": "3001",  # Host port to map
        "container_port": "11434",  # Ollama's default port
        "volume": "ollama_data"  # Named volume for the first container
    },
    {
        "name": "ollama2",
        "port": "3002",
        "host_port": "3002",  # Host port to map
        "container_port": "11434",  # Ollama's default port
        "volume": "ollama2_data"  # Separate named volume for the second container
    },
]

def run_command(command, check=True, shell=False):
    """Helper function to run a shell command."""
    try:
        process = subprocess.run(command, check=check, capture_output=True, text=True, shell=shell)
        return process
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {' '.join(command) if isinstance(command, list) else command}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise
    except FileNotFoundError:
        print(f"Error: Command '{command[0]}' not found. Is Docker installed and in PATH?")
        raise

def is_docker_daemon_running():
    """Checks if the Docker daemon is responsive."""
    try:
        run_command(["docker", "ps"], check=True)
        print("Docker daemon is running.")
        return True
    except Exception:
        print("Error: Docker daemon is not running or 'docker' command is not accessible.")
        return False

def is_container_running(container_name):
    """Checks if a container with the given name is running."""
    try:
        process = run_command(["docker", "ps", "-q", "-f", f"name=^{container_name}$"], check=False)
        return bool(process.stdout.strip())
    except Exception:
        return False  # Assuming error means not running or docker issue

def start_ollama_container(name, host_port, container_port, volume_name):
    """Starts an Ollama Docker container."""
    print(f"Attempting to start container '{name}' on host port {host_port} using volume '{volume_name}'...")
    try:
        # Ensure the named volume exists
        run_command(["docker", "volume", "create", volume_name])
        
        run_command([
            "docker", "run", "-d", "--gpus=all",
            "-v", f"{volume_name}:/root/.ollama",
            "-p", f"{host_port}:{container_port}",
            "--name", name,
            OLLAMA_IMAGE
        ])
        print(f"Container '{name}' started successfully.")
        # Wait a bit for the container to initialize
        time.sleep(5)
        return True
    except Exception as e:
        print(f"Failed to start container '{name}': {e}")
        # Attempt to remove a potentially partially created container if it exists from a failed run
        try:
            run_command(["docker", "rm", "-f", name], check=False)
        except:
            pass  # Ignore errors if removal fails
        return False

def list_models_in_container(container_name):
    """Lists models available in the specified Ollama container."""
    print(f"Listing models in container '{container_name}'...")
    try:
        process = run_command(["docker", "exec", container_name, "ollama", "list"], check=True)
        output = process.stdout
        
        # Parse the output to extract model names
        # Expected format: NAME ID SIZE MODIFIED
        # e.g., gemma:2b b50ca31a9f69 2.5 GB 2 hours ago
        models = []
        lines = output.strip().split('\n')
        if len(lines) > 1:  # Header + models
            for line in lines[1:]:  # Skip header
                match = re.match(r"^\s*([\w:\-\.]+)", line)
                if match:
                    models.append(match.group(1))
        print(f"Models found in '{container_name}': {models}")
        return models
    except Exception as e:
        print(f"Failed to list models in container '{container_name}': {e}")
        return []

def pull_model_in_container(container_name, model_name_to_pull):
    """Pulls the specified model into the container if it doesn't exist."""
    print(f"Ensuring model '{model_name_to_pull}' is available in container '{container_name}'...")
    try:
        # Check if model exists
        existing_models = list_models_in_container(container_name)
        if model_name_to_pull in existing_models:
            print(f"Model '{model_name_to_pull}' already exists in '{container_name}'.")
            return True

        print(f"Pulling model '{model_name_to_pull}' in container '{container_name}'. This may take a while...")
        # Set a longer timeout for model pulling if possible, or just let it run
        run_command(["docker", "exec", container_name, "ollama", "pull", model_name_to_pull], check=True)
        print(f"Model '{model_name_to_pull}' pulled successfully in '{container_name}'.")
        return True
    except Exception as e:
        print(f"Failed to pull model '{model_name_to_pull}' in container '{container_name}': {e}")
        return False

def delete_model_from_container(container_name, model_name_to_delete):
    """Deletes the specified model from the container."""
    print(f"Attempting to delete model '{model_name_to_delete}' from container '{container_name}'...")
    try:
        # Check if model exists before attempting to delete
        existing_models = list_models_in_container(container_name)
        if model_name_to_delete not in existing_models:
            print(f"Model '{model_name_to_delete}' does not exist in '{container_name}'. Cannot delete.")
            return False  # Or True, depending on desired idempotency for "already deleted"

        run_command(["docker", "exec", container_name, "ollama", "delete", model_name_to_delete], check=True)
        print(f"Model '{model_name_to_delete}' deleted successfully from '{container_name}'.")
        return True
    except Exception as e:
        print(f"Failed to delete model '{model_name_to_delete}' from container '{container_name}': {e}")
        return False

def initialize_ollama_services():
    """Initializes Ollama Docker containers and ensures the default model is present."""
    print("Initializing Ollama services...")
    if not is_docker_daemon_running():
        return False

    all_successful = True
    for config in CONTAINERS_CONFIG:
        container_name = config["name"]
        print(f"\nProcessing container: {container_name}")

        if not is_container_running(container_name):
            print(f"Container '{container_name}' is not running.")
            if not start_ollama_container(container_name, config["host_port"], config["container_port"], config["volume"]):
                all_successful = False
                continue  # Skip model pull if container start failed
        else:
            print(f"Container '{container_name}' is already running.")

        # Ensure container is fully up before pulling model
        time.sleep(2)  # Brief pause after check/start

        if not pull_model_in_container(container_name, DEFAULT_MODEL_NAME):
            all_successful = False
            
    if all_successful:
        print("\nOllama services initialized successfully.")
    else:
        print("\nSome Ollama services failed to initialize.")
    return all_successful

if __name__ == "__main__":
    # This allows running the script directly for testing
    if initialize_ollama_services():
        print("Initialization complete.")
    else:
        print("Initialization failed. Please check Docker setup and logs.")
        sys.exit(1)
