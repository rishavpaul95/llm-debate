from flask import Flask, render_template, request, jsonify
import requests
from flask_socketio import SocketIO
import threading
import time

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuration for the two Ollama endpoints
OLLAMA1_URL = "http://localhost:3001/api/generate"
OLLAMA2_URL = "http://localhost:3002/api/generate"

conversation = []
conversation_active = False
conversation_thread = None
debate_topic = "God's existence"  # Default topic
for_position_label = "For God LLM"
against_position_label = "Against God LLM"

def generate_system_prompts(topic):
    """Generate appropriate system prompts based on the topic"""
    for_prompt = f"You are a strong supporter and will always argue FOR {topic}. Present compelling arguments supporting this position."
    against_prompt = f"You are strongly opposed and will always argue AGAINST {topic}. Present compelling arguments opposing this position."
    return for_prompt, against_prompt

def generate_response(prompt, endpoint_url, is_for_position=True):
    """Get a response from one of the Ollama instances"""
    headers = {"Content-Type": "application/json"}
    
    # Get appropriate system prompts based on the current topic
    for_prompt, against_prompt = generate_system_prompts(debate_topic)
    
    # Define system prompts based on which LLM we're calling
    system_prompt = for_prompt if is_for_position else against_prompt
    
    # Notify clients that typing has started
    speaker = for_position_label if is_for_position else against_position_label
    socketio.emit('typing_indicator', {"speaker": speaker, "typing": True})
    
    data = {
        "model": "gemma3:4b",
        "prompt": prompt,
        "system": system_prompt,
        "stream": False
    }
    
    response = requests.post(endpoint_url, headers=headers, json=data)
    
    # Notify clients that typing has stopped
    socketio.emit('typing_indicator', {"speaker": speaker, "typing": False})
    
    if response.status_code == 200:
        return response.json().get("response", "")
    else:
        return f"Error: {response.status_code} - {response.text}"

def conversation_loop():
    """Function to run the conversation between the two LLMs"""
    global conversation, conversation_active
    
    # Initial prompt to start the conversation
    if not conversation:
        prompt = f"Hello! Let's discuss {debate_topic} today."
        conversation.append({"speaker": "Human", "message": prompt})
        socketio.emit('new_message', {"speaker": "Human", "message": prompt})
    
    turns = 0
    
    while conversation_active and turns < 10:  # Limit to 10 turns to prevent infinite loop
        # LLM 1's turn (Against position)
        last_messages = " ".join([msg["message"] for msg in conversation[-3:] if msg])
        prompt = f"Continue this conversation about {debate_topic}: {last_messages}"
        
        response1 = generate_response(prompt, OLLAMA1_URL, is_for_position=False)
        message1 = {"speaker": against_position_label, "message": response1}
        conversation.append(message1)
        socketio.emit('new_message', message1)
        
        if not conversation_active:
            break
        
        time.sleep(1)  # Small delay between responses
        
        # LLM 2's turn (For position)
        last_messages = " ".join([msg["message"] for msg in conversation[-3:] if msg])
        prompt = f"Continue this conversation about {debate_topic}: {last_messages}"
        
        response2 = generate_response(prompt, OLLAMA2_URL, is_for_position=True)
        message2 = {"speaker": for_position_label, "message": response2}
        conversation.append(message2)
        socketio.emit('new_message', message2)
        
        turns += 1
        time.sleep(1)  # Small delay between turns
    
    conversation_active = False
    socketio.emit('conversation_status', {"active": False})

@app.route('/')
def index():
    return render_template('index.html', topic=debate_topic)

@app.route('/api/conversation', methods=['GET'])
def get_conversation():
    return jsonify(conversation)

@app.route('/api/start', methods=['POST'])
def start_conversation():
    global conversation_active, conversation_thread
    
    # Only start if not already active
    if not conversation_active:
        conversation_active = True
        socketio.emit('conversation_status', {"active": True})  # Send status update to frontend
        conversation_thread = threading.Thread(target=conversation_loop)
        conversation_thread.start()
        return jsonify({"status": "started"})
    
    return jsonify({"status": "already_running"})

@app.route('/api/stop', methods=['POST'])
def stop_conversation():
    global conversation_active
    conversation_active = False
    socketio.emit('conversation_status', {"active": False})  # Send status update to frontend
    return jsonify({"status": "stopped"})

@app.route('/api/reset', methods=['POST'])
def reset_conversation():
    global conversation, conversation_active
    conversation = []
    conversation_active = False
    socketio.emit('conversation_status', {"active": False})  # Send status update to frontend
    return jsonify({"status": "reset"})

@app.route('/api/topic', methods=['POST'])
def set_topic():
    global debate_topic, conversation, conversation_active, for_position_label, against_position_label
    
    if conversation_active:
        return jsonify({"status": "error", "message": "Cannot change topic while debate is active"})
    
    topic = request.json.get("topic", "").strip()
    
    if not topic:
        return jsonify({"status": "error", "message": "Topic cannot be empty"})
    
    # Set the new topic
    debate_topic = topic
    
    # Update the position labels based on the topic
    for_position_label = f"For {topic}"
    against_position_label = f"Against {topic}"
    
    # Clear existing conversation
    conversation = []
    
    # Send topic update to all clients
    socketio.emit('topic_updated', {
        "topic": topic, 
        "for_label": for_position_label,
        "against_label": against_position_label
    })
    
    return jsonify({
        "status": "success", 
        "topic": topic,
        "for_label": for_position_label,
        "against_label": against_position_label
    })

@socketio.on('connect')
def handle_connect():
    socketio.emit('conversation_status', {"active": conversation_active})
    socketio.emit('topic_info', {
        "topic": debate_topic,
        "for_label": for_position_label,
        "against_label": against_position_label
    })
    for msg in conversation:
        socketio.emit('new_message', msg)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
