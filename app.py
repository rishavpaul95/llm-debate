from flask import Flask, render_template, request, jsonify, session
import requests
from flask_socketio import SocketIO, join_room, leave_room
import threading
import time
import json
import uuid
from collections import defaultdict
import sys # For sys.exit

# Import the Docker initialization script
from initialize_docker import initialize_ollama_services

app = Flask(__name__)
app.config['SECRET_KEY'] = 'llm-debate-secret-key'  # Needed for session management
# Change async_mode to threading for Python 3.12 compatibility
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Configuration for the two Ollama endpoints
OLLAMA1_URL = "http://localhost:3001/api/generate"
OLLAMA2_URL = "http://localhost:3002/api/generate"

# Session-based storage for conversations
sessions = {}

# Lock for thread safety when accessing sessions
session_lock = threading.Lock()

# Map Flask session IDs to SocketIO session IDs for persistence
flask_to_socketio_map = {}

def generate_system_prompts(topic):
    """Generate appropriate system prompts based on the topic"""
    for_prompt = f"You are a strong supporter and will always argue FOR {topic}. Present compelling arguments supporting this position."
    against_prompt = f"You are strongly opposed and will always argue AGAINST {topic}. Present compelling arguments opposing this position."
    return for_prompt, against_prompt

def generate_response(prompt, endpoint_url, session_id, is_for_position=True):
    """Get a response from one of the Ollama instances using streaming"""
    # Get session data
    with session_lock:
        if session_id not in sessions:
            return "Session expired"
        session_data = sessions[session_id]
        topic = session_data['topic']
        for_position_label = session_data['for_position_label']
        against_position_label = session_data['against_position_label']
    
    headers = {"Content-Type": "application/json"}
    
    # Get appropriate system prompts based on the current topic
    for_prompt, against_prompt = generate_system_prompts(topic)
    
    # Define system prompts based on which LLM we're calling
    system_prompt = for_prompt if is_for_position else against_prompt
    
    # Notify clients that typing has started
    speaker = for_position_label if is_for_position else against_position_label
    socketio.emit('typing_indicator', {"speaker": speaker, "typing": True}, room=session_id)
    
    data = {
        "model": "gemma3:4b",
        "prompt": prompt,
        "system": system_prompt,
        "stream": True,
        "max_tokens": 350  # Limit output to about 4 paragraphs (approx. 350 tokens)
    }
    
    # Create a unique message ID for this streaming response
    message_id = f"{int(time.time() * 1000)}-{speaker}"
    full_response = ""
    
    try:
        with requests.post(endpoint_url, headers=headers, json=data, stream=True) as response:
            if response.status_code != 200:
                # Handle error case
                error_msg = f"Error: {response.status_code} - {response.text}"
                socketio.emit('stream_message', {
                    "speaker": speaker,
                    "message": error_msg,
                    "message_id": message_id,
                    "done": True
                }, room=session_id)
                return error_msg
            
            # Process the streaming response
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        if 'response' in chunk:
                            chunk_text = chunk['response']
                            full_response += chunk_text
                            
                            # Verify session still exists
                            with session_lock:
                                if session_id not in sessions:
                                    break
                            
                            # Emit the chunk to the frontend
                            socketio.emit('stream_message', {
                                "speaker": speaker,
                                "message": chunk_text,
                                "message_id": message_id,
                                "done": chunk.get('done', False)
                            }, room=session_id)
                            
                            # Add a small sleep to prevent overwhelming the frontend
                            time.sleep(0.01)
                        
                        # If this is the last chunk, break the loop
                        if chunk.get('done', False):
                            break
                    except json.JSONDecodeError:
                        continue

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        # Verify session still exists
        with session_lock:
            if session_id in sessions:
                socketio.emit('stream_message', {
                    "speaker": speaker,
                    "message": error_msg,
                    "message_id": message_id,
                    "done": True
                }, room=session_id)
        return error_msg
    
    # Notify clients that typing has stopped
    with session_lock:
        if session_id in sessions:
            socketio.emit('typing_indicator', {"speaker": speaker, "typing": False}, room=session_id)
    
    return full_response

def conversation_loop(session_id):
    """Function to run the conversation between the two LLMs for a specific session"""
    with session_lock:
        if session_id not in sessions:
            return
        
        session_data = sessions[session_id]
        conversation = session_data['conversation']
        topic = session_data['topic']
        for_position_label = session_data['for_position_label']
        against_position_label = session_data['against_position_label']
    
    # Initial prompt only if conversation is empty
    if not conversation:
        prompt = f"Hello! Let's discuss {topic} today."
        with session_lock:
            if session_id in sessions:
                # Add timestamp to ensure proper ordering
                sessions[session_id]['conversation'].append({
                    "speaker": "Human", 
                    "message": prompt,
                    "timestamp": time.time()
                })
                socketio.emit('new_message', {"speaker": "Human", "message": prompt}, room=session_id)
    
    turns = 0
    
    while True:
        # Check if the session still exists or has been stopped
        with session_lock:
            if session_id not in sessions or not sessions[session_id]['active']:
                break
            
            conversation = sessions[session_id]['conversation']
            topic = sessions[session_id]['topic']
        
        # Limit to 10 turns to prevent infinite loop
        if turns >= 10:
            break
        
        # LLM 1's turn (Against position)
        last_messages = " ".join([msg["message"] for msg in conversation[-3:] if msg])
        prompt = f"Continue this conversation about {topic}: {last_messages}"
        
        response1 = generate_response(prompt, OLLAMA1_URL, session_id, is_for_position=False)
        
        # Check if session still exists
        with session_lock:
            if session_id not in sessions or not sessions[session_id]['active']:
                break
            
            message1 = {
                "speaker": against_position_label, 
                "message": response1,
                "timestamp": time.time()
            }
            sessions[session_id]['conversation'].append(message1)
        
        time.sleep(1)  # Small delay between responses
        
        # Check if session still exists
        with session_lock:
            if session_id not in sessions or not sessions[session_id]['active']:
                break
            
            conversation = sessions[session_id]['conversation']
            topic = sessions[session_id]['topic']
        
        # LLM 2's turn (For position)
        last_messages = " ".join([msg["message"] for msg in conversation[-3:] if msg])
        prompt = f"Continue this conversation about {topic}: {last_messages}"
        
        response2 = generate_response(prompt, OLLAMA2_URL, session_id, is_for_position=True)
        
        # Check if session still exists
        with session_lock:
            if session_id not in sessions or not sessions[session_id]['active']:
                break
            
            message2 = {
                "speaker": for_position_label, 
                "message": response2,
                "timestamp": time.time()
            }
            sessions[session_id]['conversation'].append(message2)
        
        turns += 1
        time.sleep(1)  # Small delay between turns
    
    # Set conversation to inactive when done
    with session_lock:
        if session_id in sessions:
            sessions[session_id]['active'] = False
            socketio.emit('conversation_status', {"active": False}, room=session_id)

@app.route('/')
def index():
    # Generate a persistent session ID if one doesn't exist
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    flask_session_id = session['session_id']
    
    # Check if we already have a socketio session mapped to this flask session
    socketio_session_id = None
    with session_lock:
        if flask_session_id in flask_to_socketio_map:
            socketio_session_id = flask_to_socketio_map[flask_session_id]
            # Verify this session actually exists
            if socketio_session_id not in sessions:
                # If not, remove the mapping
                del flask_to_socketio_map[flask_session_id]
                socketio_session_id = None
    
    return render_template('index.html', 
                          session_id=flask_session_id,
                          socketio_session_id=socketio_session_id)

@app.route('/api/conversation', methods=['GET'])
def get_conversation():
    session_id = request.args.get('session_id')
    if not session_id or session_id not in sessions:
        return jsonify([])
    
    with session_lock:
        conversation = sessions[session_id]['conversation'] if session_id in sessions else []
    
    return jsonify(conversation)

@app.route('/api/start', methods=['POST'])
def start_conversation():
    session_id = request.json.get('session_id')
    
    if not session_id or session_id not in sessions:
        return jsonify({"status": "error", "message": "Invalid session"})
    
    with session_lock:
        # Only start if not already active
        if not sessions[session_id]['active']:
            sessions[session_id]['active'] = True
            socketio.emit('conversation_status', {"active": True}, room=session_id)
            
            # Start conversation in a new thread
            conversation_thread = threading.Thread(
                target=conversation_loop, 
                args=(session_id,)
            )
            conversation_thread.daemon = True
            conversation_thread.start()
            
            return jsonify({"status": "started"})
        
        return jsonify({"status": "already_running"})

@app.route('/api/stop', methods=['POST'])
def stop_conversation():
    session_id = request.json.get('session_id')
    
    if not session_id or session_id not in sessions:
        return jsonify({"status": "error", "message": "Invalid session"})
    
    with session_lock:
        if session_id in sessions:
            sessions[session_id]['active'] = False
            socketio.emit('conversation_status', {"active": False}, room=session_id)
    
    return jsonify({"status": "stopped"})

@app.route('/api/reset', methods=['POST'])
def reset_conversation():
    session_id = request.json.get('session_id')
    
    if not session_id or session_id not in sessions:
        return jsonify({"status": "error", "message": "Invalid session"})
    
    with session_lock:
        if session_id in sessions:
            sessions[session_id]['conversation'] = []
            sessions[session_id]['active'] = False
            socketio.emit('conversation_status', {"active": False}, room=session_id)
    
    return jsonify({"status": "reset"})

@app.route('/api/topic', methods=['POST'])
def set_topic():
    session_id = request.json.get('session_id')
    topic = request.json.get("topic", "").strip()
    
    if not session_id or session_id not in sessions:
        return jsonify({"status": "error", "message": "Invalid session"})
    
    if not topic:
        return jsonify({"status": "error", "message": "Topic cannot be empty"})
    
    with session_lock:
        session_data = sessions[session_id]
        
        if session_data['active']:
            return jsonify({"status": "error", "message": "Cannot change topic while debate is active"})
        
        # Set the new topic
        session_data['topic'] = topic
        
        # Update the position labels based on the topic
        session_data['for_position_label'] = f"For {topic}"
        session_data['against_position_label'] = f"Against {topic}"
        
        # Clear existing conversation
        session_data['conversation'] = []
        
        # Send topic update to clients in this session
        socketio.emit('topic_updated', {
            "topic": topic, 
            "for_label": session_data['for_position_label'],
            "against_label": session_data['against_position_label']
        }, room=session_id)
    
    return jsonify({
        "status": "success", 
        "topic": topic,
        "for_label": f"For {topic}",
        "against_label": f"Against {topic}"
    })

@socketio.on('connect')
def handle_connect():
    # Get Flask session ID (from URL params or cookie)
    flask_session_id = request.args.get('flask_session_id')
    if not flask_session_id:
        try:
            flask_session_id = session.get('session_id')
        except:
            flask_session_id = None
    
    # Get any existing socketio session mapped to this Flask session
    socketio_session_id = None
    if flask_session_id:
        with session_lock:
            socketio_session_id = flask_to_socketio_map.get(flask_session_id)
    
    # If we have a valid mapping and session exists, use it
    if socketio_session_id and socketio_session_id in sessions:
        session_id = socketio_session_id
    else:
        # Otherwise create a new session with the socket.io ID
        session_id = request.sid
        
        # Map the Flask session ID to this new SocketIO session ID
        if flask_session_id:
            with session_lock:
                flask_to_socketio_map[flask_session_id] = session_id
        
        # Initialize new session
        with session_lock:
            if session_id not in sessions:
                default_topic = "God's existence"
                sessions[session_id] = {
                    'conversation': [],
                    'active': False,
                    'topic': default_topic,
                    'for_position_label': f"For {default_topic}",
                    'against_position_label': f"Against {default_topic}",
                    'flask_session_id': flask_session_id  # Store association
                }
    
    # Join the room with the session ID
    join_room(session_id)
    
    # Send initial data to the client
    with session_lock:
        if session_id in sessions:  # Verify session still exists
            session_data = sessions[session_id]
            
            # Send session initialization data
            socketio.emit('session_init', {
                "session_id": session_id
            }, room=session_id)
            
            # Send conversation status
            socketio.emit('conversation_status', {
                "active": session_data['active']
            }, room=session_id)
            
            # Send topic information
            socketio.emit('topic_info', {
                "topic": session_data['topic'],
                "for_label": session_data['for_position_label'],
                "against_label": session_data['against_position_label']
            }, room=session_id)
            
            # If there are existing messages, send them to the client in proper order
            if session_data['conversation']:
                # Make sure the messages are in chronological order (oldest to newest)
                ordered_messages = sorted(
                    session_data['conversation'],
                    key=lambda msg: msg.get('timestamp', 0) if isinstance(msg, dict) else 0
                )
                socketio.emit('conversation_history', {
                    "messages": ordered_messages
                }, room=session_id)

@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    # Clean up resources but keep the session data for a while
    # (could add a cleanup timer to remove inactive sessions after a period)
    with session_lock:
        if session_id in sessions:
            sessions[session_id]['active'] = False
    leave_room(session_id)

if __name__ == '__main__':
    print("Attempting to initialize Docker services for Ollama...")
    if not initialize_ollama_services():
        print("Failed to initialize Docker services. Please check Docker is running and configured correctly.")
        print("Exiting application.")
        sys.exit(1)
    
    print("Docker services initialized. Starting LLM Debate Application...")
    print("Server running on http://localhost:5000")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
