# Dynamic LLM Debate Application

This application creates a debate between two LLMs with opposing viewpoints on any topic you choose. Simply enter your topic, and the LLMs will take opposing positions in a real-time debate.

## Prerequisites

- **Docker**: Ensure Docker is installed and the Docker daemon is running on your system. The user running the application should have permissions to interact with Docker.
- **GPU (Recommended for Ollama)**: For optimal performance with Ollama, a compatible GPU and necessary drivers (e.g., NVIDIA drivers for `--gpus=all`) should be installed.

## Setup Instructions

### 1. Clone the Repository (if you haven't already)
```bash
# git clone <repository_url>
# cd <repository_directory>
```

### 2. Install Python Dependencies
```bash
# Install required Python packages
pip install -r requirements.txt
```

### 3. Run the Flask Application
```bash
# Start the Flask application
python app.py
```
The application will automatically attempt to:
- Start two Ollama Docker containers (`ollama` on host port 3001 and `ollama2` on host port 3002) if they are not already running.
- Pull the `gemma3:4b` model into each container if it's not already present. (Note: `gemma3:4b` is used as per original setup; if this model name is incorrect or unavailable, you can adjust `MODEL_NAME` in `initialize_docker.py`).

If Docker is not running or there are issues with the setup, the script will output error messages.

### 4. Access the Application

Open your web browser and go to:
```
http://localhost:5000
```

## Using the Application

1. **Enter a Topic**: Type any debate topic in the input field and click "Set Topic"
2. **Configure Settings (Optional)**: Click the "Settings" button to:
    - Select specific Ollama models for the "For" and "Against" debaters.
    - Pull new models into the Ollama instances.
    - Set the "Number of Exchanges" for the debate (default is 1, range 1-5). Each exchange consists of one statement from each debater.
3. **Start the Debate**: Click "Start Debate" to begin the conversation
4. **Watch the Debate**: See the LLMs take opposing positions on your chosen topic
5. **Control the Debate**: Use the Stop and Reset buttons to control the flow

Your session will persist even if you refresh the page or close and reopen your browser. Each visitor to the site gets their own private debate session.

## Example Topics

Try these topics for interesting debates:
- Climate change
- Artificial intelligence
- Universal healthcare
- Cryptocurrency
- Space exploration
- Veganism
- Remote work
- Nuclear energy
- Social media regulation
- Genetic engineering

## Key Features

- **Persistent Sessions**: Your debate continues exactly where you left off if you refresh the page
- **Multi-User Support**: Each visitor gets their own independent debate session
- **Dynamic Topics**: Set any topic you want the LLMs to debate
- **Configurable Models**: Choose different Ollama models for each debater.
- **Configurable Number of Debate Exchanges**: Set how many rounds of back-and-forth the debate will have.
- **Real-time Updates**: See the conversation unfold with live typing indicators
- **Responsive Design**: Works on desktops, tablets, and mobile devices
- **Visual Differentiation**: Each side of the debate has distinct visual styling
- **Message Ordering**: Messages are always presented in the correct chronological order
- **Automated Docker Setup**: The application attempts to initialize required Docker containers and Ollama models on startup.

## Technical Details

- **Backend**: Flask with Flask-SocketIO for real-time communication
- **Session Management**: Persistent sessions using Flask sessions and localStorage
- **Communication with LLMs**: REST API calls to Ollama endpoints with dynamic system prompts
- **Frontend**: HTML/CSS/JS with WebSocket updates and responsive design
- **Conversation Tracking**: Timestamps ensure proper message ordering

## How It Works

The application dynamically generates appropriate system prompts based on your chosen topic. You can also select specific Ollama models for each debater and configure the number of exchanges (turns) for the debate via the "Settings" panel.

- **For Position LLM**:
    - Uses Ollama Instance 1 (running on host port `3001`, container name `ollama`).
    - Receives a prompt to argue in favor of the topic.
- **Against Position LLM**:
    - Uses Ollama Instance 2 (running on host port `3002`, container name `ollama2`).
    - Receives a prompt to argue against the topic.

The system ensures that each LLM maintains its assigned perspective throughout the conversation, creating a balanced and engaging debate.

## Browser Compatibility

- Chrome, Firefox, Safari, Edge (latest versions)
- Works on desktop and mobile devices
- Maintains session state across page refreshes and browser restarts

## Manual Docker Management (Optional)

If you prefer to manage Docker containers manually or troubleshoot, here are the commands the script attempts to automate:

**Named Volumes (created automatically by the script):**
- `ollama_data` (for `ollama` container)
- `ollama2_data` (for `ollama2` container)

**To start containers manually:**
```bash
# Create volumes if they don't exist
docker volume create ollama_data
docker volume create ollama2_data

# Start the first container (Against position LLM)
docker run -d --gpus=all -v ollama_data:/root/.ollama -p 3001:11434 --name ollama ollama/ollama

# Start the second container (For position LLM) 
docker run -d --gpus=all -v ollama2_data:/root/.ollama -p 3002:11434 --name ollama2 ollama/ollama
```

**To pull models manually into containers:**
```bash
# Pull model into the first container
docker exec ollama ollama pull gemma3:4b

# Pull model into the second container
docker exec ollama2 ollama pull gemma3:4b
```
