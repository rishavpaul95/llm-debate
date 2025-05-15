# Dynamic LLM Debate Application

This application creates a debate between two LLMs with opposing viewpoints on any topic you choose. Simply enter your topic, and the LLMs will take opposing positions in a real-time debate.

## Setup Instructions

### 1. Docker Setup

First, start two Ollama containers on different ports:

```bash
# Start the first container (Against position LLM)
docker run -d --gpus=all -v ollama:/root/.ollama -p 3001:11434 --name ollama ollama/ollama

# Start the second container (For position LLM) 
docker run -d --gpus=all -v ollama:/root/.ollama -p 3002:11434 --name ollama2 ollama/ollama
```

### 2. Set Up the Models

Run the following commands to initialize both LLMs:

```bash
# Enter the first container
docker exec -it ollama ollama run gemma3:4b

# Exit the Ollama prompt (it will automatically be configured by the app)
exit

# Enter the second container
docker exec -it ollama2 ollama run gemma3:4b

# Exit the Ollama prompt (it will automatically be configured by the app)
exit
```

### 3. Run the Flask Application

Install requirements and start the application:

```bash
# Install required Python packages
pip install -r requirements.txt

# Start the Flask application
python app.py
```

### 4. Access the Application

Open your web browser and go to:
```
http://localhost:5000
```

## Using the Application

1. **Enter a Topic**: Type any debate topic in the input field and click "Set Topic"
2. **Start the Debate**: Click "Start Debate" to begin the conversation
3. **Watch the Debate**: See the LLMs take opposing positions on your chosen topic
4. **Control the Debate**: Use the Stop and Reset buttons to control the flow

Example topics you can try:
- Climate change
- Artificial intelligence
- Universal healthcare
- Cryptocurrency
- Space exploration
- Veganism
- Remote work

## Application Features

- **Dynamic Topics**: Set any topic you want the LLMs to debate
- **Real-time Updates**: See the conversation unfold in real-time
- **Automatic Perspective Assignment**: LLMs automatically take opposing positions
- **Visual Differentiation**: Each side of the debate has distinct visual styling

## Technical Details

- Backend: Flask with Flask-SocketIO for real-time communication
- Communication with LLMs: REST API calls to Ollama endpoints with dynamic system prompts
- Frontend: HTML/CSS/JS with WebSocket updates

## How It Works

The application dynamically generates appropriate system prompts based on your chosen topic:

- **For Position LLM**: Receives a prompt to argue in favor of the topic
- **Against Position LLM**: Receives a prompt to argue against the topic

The system ensures that each LLM maintains its assigned perspective throughout the conversation, creating a balanced and engaging debate.
