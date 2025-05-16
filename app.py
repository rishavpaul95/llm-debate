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
from initialize_docker import initialize_ollama_services, list_models_in_container, pull_model_in_container as pull_docker_model, delete_model_from_container, DEFAULT_MODEL_NAME

app = Flask(__name__)
app.config['SECRET_KEY'] = 'llm-debate-secret-key'  # Needed for session management
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# For LLM -> Ollama Instance 1 (ollama, port 3001)
# Against LLM -> Ollama Instance 2 (ollama2, port 3002)
OLLAMA_FOR_URL = "http://localhost:3001/api/generate" # Instance 1 for "For"
OLLAMA_AGAINST_URL = "http://localhost:3002/api/generate" # Instance 2 for "Against"

# Helper to get base URLs for API calls like delete, show, etc.
OLLAMA_FOR_BASE_URL = OLLAMA_FOR_URL.replace("/api/generate", "")
OLLAMA_AGAINST_BASE_URL = OLLAMA_AGAINST_URL.replace("/api/generate", "")

OLLAMA_FOR_CONTAINER_NAME = "ollama"
OLLAMA_AGAINST_CONTAINER_NAME = "ollama2"

sessions = {}
session_lock = threading.Lock()
flask_to_socketio_map = {}

# Global flag to indicate if a long Ollama operation (pull/delete) is in progress
is_long_ollama_operation_active = False
long_op_lock = threading.Lock()

USER_SPECIFIED_PULLABLE_MODELS = ["qwen3:4b", "llama3.2:3b", "qwen2.5vl:3b"]
PULLABLE_MODELS_LIST = [m for m in USER_SPECIFIED_PULLABLE_MODELS if m != DEFAULT_MODEL_NAME]

def generate_system_prompts(topic):
    for_prompt = f"You are a strong supporter and will always argue FOR {topic}. Present compelling arguments supporting this position."
    against_prompt = f"You are strongly opposed and will always argue AGAINST {topic}. Present compelling arguments opposing this position."
    return for_prompt, against_prompt

def generate_response(prompt, session_id, for_model_name, against_model_name, is_for_position=True):
    """Get a response from one of the Ollama instances using streaming"""
    with session_lock:
        if session_id not in sessions:
            return "Session expired"
        session_data = sessions[session_id]
        topic = session_data['topic']
        for_position_label = session_data['for_position_label']
        against_position_label = session_data['against_position_label']
        
    # Determine endpoint and model based on position
    if is_for_position:
        endpoint_url = OLLAMA_FOR_URL
        current_model_name = for_model_name
        speaker = for_position_label
    else: # Against position
        endpoint_url = OLLAMA_AGAINST_URL
        current_model_name = against_model_name
        speaker = against_position_label
            
    headers = {"Content-Type": "application/json"}
    for_prompt, against_prompt = generate_system_prompts(topic)
    system_prompt = for_prompt if is_for_position else against_prompt
    
    socketio.emit('typing_indicator', {"speaker": speaker, "typing": True}, room=session_id)
    
    data = {
        "model": current_model_name,
        "prompt": prompt,
        "system": system_prompt,
        "stream": True,
        "max_tokens": 350
    }
    
    message_id = f"{int(time.time() * 1000)}-{speaker}"
    full_response = ""
    
    try:
        with requests.post(endpoint_url, headers=headers, json=data, stream=True) as response:
            if response.status_code != 200:
                error_msg = f"Error: {response.status_code} - {response.text}"
                socketio.emit('stream_message', {
                    "speaker": speaker,
                    "message": error_msg,
                    "message_id": message_id,
                    "done": True
                }, room=session_id)
                return error_msg
            
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        if 'response' in chunk:
                            chunk_text = chunk['response']
                            full_response += chunk_text
                            
                            with session_lock:
                                if session_id not in sessions:
                                    break
                            
                            socketio.emit('stream_message', {
                                "speaker": speaker,
                                "message": chunk_text,
                                "message_id": message_id,
                                "done": chunk.get('done', False)
                            }, room=session_id)
                            
                            time.sleep(0.01)
                        
                        if chunk.get('done', False):
                            break
                    except json.JSONDecodeError:
                        continue

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        with session_lock:
            if session_id in sessions:
                socketio.emit('stream_message', {
                    "speaker": speaker,
                    "message": error_msg,
                    "message_id": message_id,
                    "done": True
                }, room=session_id)
        return error_msg
    
    with session_lock:
        if session_id in sessions:
            socketio.emit('typing_indicator', {"speaker": speaker, "typing": False}, room=session_id)
    
    return full_response

def generate_evaluation_response(prompt_text, session_id):
    """Get an evaluation response from an Ollama instance using streaming."""
    speaker = "Evaluator"
    system_prompt_eval = "You will be shown a debate conversation. Your task is to determine who won the debate and provide a concise explanation for your decision. Focus on the strength of arguments, rebuttals, and overall persuasiveness. Avoid simply summarizing the debate."
    endpoint_url = OLLAMA_FOR_URL # Use one of the instances
    current_model_name = DEFAULT_MODEL_NAME

    socketio.emit('typing_indicator', {"speaker": speaker, "typing": True}, room=session_id)
    
    headers = {"Content-Type": "application/json"}
    data = {
        "model": current_model_name,
        "prompt": prompt_text,
        "system": system_prompt_eval,
        "stream": True,
        "max_tokens": 400 # Slightly more tokens for evaluation
    }
    
    message_id = f"{int(time.time() * 1000)}-{speaker}"
    full_response_text = ""
    
    try:
        with requests.post(endpoint_url, headers=headers, json=data, stream=True) as response:
            if response.status_code != 200:
                error_msg = f"Error: {response.status_code} - {response.text}"
                socketio.emit('stream_message', {
                    "speaker": speaker,
                    "message": error_msg,
                    "message_id": message_id,
                    "done": True
                }, room=session_id)
                return error_msg
            
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        if 'response' in chunk:
                            chunk_text = chunk['response']
                            full_response_text += chunk_text
                            
                            with session_lock:
                                if session_id not in sessions: # Check if session still exists
                                    break 
                            
                            socketio.emit('stream_message', {
                                "speaker": speaker,
                                "message": chunk_text,
                                "message_id": message_id,
                                "done": chunk.get('done', False)
                            }, room=session_id)
                            
                            time.sleep(0.01)
                        
                        if chunk.get('done', False):
                            break
                    except json.JSONDecodeError:
                        continue # Ignore malformed JSON lines

    except Exception as e:
        error_msg = f"Error during evaluation: {str(e)}"
        with session_lock:
            if session_id in sessions:
                socketio.emit('stream_message', {
                    "speaker": speaker,
                    "message": error_msg,
                    "message_id": message_id,
                    "done": True
                }, room=session_id)
        return error_msg
    
    with session_lock:
        if session_id in sessions: # Check if session still exists
            socketio.emit('typing_indicator', {"speaker": speaker, "typing": False}, room=session_id)
    
    return full_response_text

def evaluate_debate(session_id):
    with session_lock:
        if session_id not in sessions:
            return
        session_data = sessions[session_id]
        conversation_history = session_data['conversation']
        # Ensure no active debate during evaluation to prevent race conditions
        if session_data['active']: 
            print(f"Warning: evaluate_debate called for session {session_id} while still active.")
            return


    # Announce evaluation phase
    system_message_text = "The debate has concluded. An impartial evaluator will now determine the winner and provide an analysis."
    system_message = {
        "speaker": "System",
        "message": system_message_text,
        "timestamp": time.time()
    }
    with session_lock:
        if session_id in sessions:
            sessions[session_id]['conversation'].append(system_message)
    socketio.emit('new_message', system_message, room=session_id)
    time.sleep(0.5) # Small delay for the message to appear

    # Prepare conversation text for the evaluator
    # Exclude the "System" announcement message itself from the text sent for evaluation
    debate_text_for_evaluator = "\n\n".join([
        f"{msg['speaker']}: {msg['message']}" 
        for msg in conversation_history 
        if msg['speaker'] != "System" # Exclude system messages from evaluation content
    ])
    
    if not debate_text_for_evaluator.strip():
        print(f"No debate content to evaluate for session {session_id}.")
        return

    evaluation_prompt = f"Here is the debate transcript:\n\n{debate_text_for_evaluator}\n\nBased on this transcript, who won the debate and why?"
    
    evaluator_response = generate_evaluation_response(evaluation_prompt, session_id)

    with session_lock:
        if session_id in sessions:
            sessions[session_id]['conversation'].append({
                "speaker": "Evaluator",
                "message": evaluator_response,
                "timestamp": time.time()
            })
            # Ensure debate remains inactive after evaluation
            sessions[session_id]['active'] = False 
            socketio.emit('conversation_status', {
                "active": False,
                "is_long_ollama_operation_active": is_long_ollama_operation_active 
            }, room=session_id)

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
        selected_for_model = session_data.get('selected_for_model', DEFAULT_MODEL_NAME)
        selected_against_model = session_data.get('selected_against_model', DEFAULT_MODEL_NAME)

    if not conversation:
        prompt = f"Hello! Let's discuss {topic} today."
        with session_lock:
            if session_id in sessions:
                sessions[session_id]['conversation'].append({
                    "speaker": "Human", 
                    "message": prompt,
                    "timestamp": time.time()
                })
                socketio.emit('new_message', {"speaker": "Human", "message": prompt}, room=session_id)
    
    turns = 0
    max_turns = 3 # Define max_turns for clarity
    
    while True:
        with session_lock:
            if session_id not in sessions or not sessions[session_id]['active']:
                break
            
            conversation = sessions[session_id]['conversation']
            topic = sessions[session_id]['topic']
        
        if turns >= max_turns: # Use max_turns
            break
        
        last_messages = " ".join([msg["message"] for msg in conversation[-3:] if msg])
        prompt = f"Continue this conversation about {topic}: {last_messages}"
        
        # "For" LLM's turn (Instance 1)
        response_for = generate_response(prompt, session_id, selected_for_model, selected_against_model, is_for_position=True)
        
        with session_lock:
            if session_id not in sessions or not sessions[session_id]['active']:
                break
            
            message_for = {
                "speaker": for_position_label, 
                "message": response_for,
                "timestamp": time.time()
            }
            sessions[session_id]['conversation'].append(message_for)
        
        time.sleep(1)
        
        with session_lock:
            if session_id not in sessions or not sessions[session_id]['active']:
                break
            
            conversation = sessions[session_id]['conversation']
            topic = sessions[session_id]['topic']
        
        last_messages = " ".join([msg["message"] for msg in conversation[-3:] if msg])
        prompt = f"Continue this conversation about {topic}: {last_messages}"
        
        # "Against" LLM's turn (Instance 2)
        response_against = generate_response(prompt, session_id, selected_for_model, selected_against_model, is_for_position=False)
        
        with session_lock:
            if session_id not in sessions or not sessions[session_id]['active']:
                break
            
            message_against = {
                "speaker": against_position_label, 
                "message": response_against,
                "timestamp": time.time()
            }
            sessions[session_id]['conversation'].append(message_against)
        
        turns += 1
        time.sleep(1)
    
    # After the loop finishes
    with session_lock:
        if session_id in sessions:
            # Mark debate as inactive before evaluation
            sessions[session_id]['active'] = False
            socketio.emit('conversation_status', {
                "active": False,
                "is_long_ollama_operation_active": is_long_ollama_operation_active # Pass current global op status
                }, room=session_id)
            
            # Check if the loop ended due to max_turns, not external stop
            # This ensures evaluation only happens if the debate ran its course
            if turns >= max_turns:
                # Call evaluation in a new thread to avoid blocking
                eval_thread = threading.Thread(target=evaluate_debate, args=(session_id,))
                eval_thread.daemon = True
                eval_thread.start()
            else:
                print(f"Debate for session {session_id} ended before max turns. No evaluation.")
        else:
            print(f"Session {session_id} not found after conversation loop. No evaluation.")

@app.route('/')
def index():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    flask_session_id = session['session_id']
    
    socketio_session_id = None
    with session_lock:
        if flask_session_id in flask_to_socketio_map:
            socketio_session_id = flask_to_socketio_map[flask_session_id]
            if socketio_session_id not in sessions:
                del flask_to_socketio_map[flask_session_id]
                socketio_session_id = None
    
    return render_template('index.html', 
                          session_id=flask_session_id,
                          socketio_session_id=socketio_session_id)

@app.route('/api/models/<instance_name>', methods=['GET'])
def get_available_models(instance_name):
    container_name = ""
    if instance_name == "ollama1": # For LLM
        container_name = OLLAMA_FOR_CONTAINER_NAME
    elif instance_name == "ollama2": # Against LLM
        container_name = OLLAMA_AGAINST_CONTAINER_NAME
    else:
        return jsonify({"error": "Invalid instance name"}), 400
    
    models = list_models_in_container(container_name)
    return jsonify({"models": models, "pullable_models": PULLABLE_MODELS_LIST})

@app.route('/api/pull_model', methods=['POST'])
def pull_model_api():
    global is_long_ollama_operation_active
    data = request.json
    session_id_req = data.get('session_id') # session_id from request
    instance_name = data.get('instance_name')
    model_to_pull = data.get('model_name')

    if not instance_name or not model_to_pull:
        return jsonify({"status": "error", "message": "Instance name and model name are required"}), 400

    # Check if debate is active for this session
    if session_id_req and session_id_req in sessions:
        with session_lock:
            if sessions[session_id_req].get('active', False):
                return jsonify({"status": "error", "message": "Cannot pull models while a debate is active in your session."}), 400
    
    with long_op_lock:
        if is_long_ollama_operation_active:
            return jsonify({"status": "error", "message": "Another model operation is already in progress. Please wait."}), 400
        is_long_ollama_operation_active = True
    
    socketio.emit('long_ollama_operation_status', {"is_active": True}) # Notify all clients

    container_name = ""
    if instance_name == "ollama1": # For LLM
        container_name = OLLAMA_FOR_CONTAINER_NAME
    elif instance_name == "ollama2": # Against LLM
        container_name = OLLAMA_AGAINST_CONTAINER_NAME
    else:
        return jsonify({"status": "error", "message": "Invalid instance name"}), 400

    try:
        success = pull_docker_model(container_name, model_to_pull)
        if success:
            updated_models = list_models_in_container(container_name)
            # Emit to specific session if session_id_req is available, otherwise broadcast (or handle more granularly)
            target_room = session_id_req if session_id_req else None 
            socketio.emit('models_updated', {
                "instance_name": instance_name, 
                "models": updated_models
            }, room=target_room)
            return jsonify({"status": "success", "message": f"Model '{model_to_pull}' pulled successfully for {instance_name}."})
        else:
            return jsonify({"status": "error", "message": f"Failed to pull model '{model_to_pull}' for {instance_name}."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        with long_op_lock:
            is_long_ollama_operation_active = False
        socketio.emit('long_ollama_operation_status', {"is_active": False}) # Notify all clients

@app.route('/api/delete_model', methods=['POST'])
def delete_model_api():
    global is_long_ollama_operation_active
    data = request.json
    session_id_req = data.get('session_id')
    instance_name = data.get('instance_name')
    model_to_delete = data.get('model_name')

    if not instance_name or not model_to_delete:
        return jsonify({"status": "error", "message": "Instance name and model name are required"}), 400

    if model_to_delete == DEFAULT_MODEL_NAME:
        return jsonify({"status": "error", "message": f"Cannot delete the default model '{DEFAULT_MODEL_NAME}'. Please select a different model to delete."}), 400

    if session_id_req and session_id_req in sessions:
        with session_lock:
            if sessions[session_id_req].get('active', False):
                return jsonify({"status": "error", "message": "Cannot delete models while a debate is active in your session."}), 400
    
    with long_op_lock:
        if is_long_ollama_operation_active:
            return jsonify({"status": "error", "message": "Another model operation is already in progress. Please wait."}), 400
        is_long_ollama_operation_active = True
    
    socketio.emit('long_ollama_operation_status', {"is_active": True})

    ollama_base_url_to_call = ""
    container_name_for_listing = "" 

    if instance_name == "ollama1": 
        ollama_base_url_to_call = OLLAMA_FOR_BASE_URL
        container_name_for_listing = OLLAMA_FOR_CONTAINER_NAME
    elif instance_name == "ollama2": 
        ollama_base_url_to_call = OLLAMA_AGAINST_BASE_URL
        container_name_for_listing = OLLAMA_AGAINST_CONTAINER_NAME
    else:
        with long_op_lock: 
            is_long_ollama_operation_active = False
        socketio.emit('long_ollama_operation_status', {"is_active": False})
        return jsonify({"status": "error", "message": "Invalid instance name"}), 400

    try:
        success = delete_model_from_container(ollama_base_url_to_call, model_to_delete)
        updated_models = list_models_in_container(container_name_for_listing)
        target_room = session_id_req if session_id_req else None
        socketio.emit('models_updated', {
            "instance_name": instance_name, 
            "models": updated_models
        }, room=target_room)

        if success:
            with session_lock:
                if session_id_req and session_id_req in sessions:
                    session_data = sessions[session_id_req]
                    made_selection_change = False

                    def get_fallback_model(current_selection, deleted_model, available_models_after_delete):
                        if current_selection == deleted_model:
                            if DEFAULT_MODEL_NAME in available_models_after_delete:
                                return DEFAULT_MODEL_NAME, True
                            elif available_models_after_delete: 
                                return available_models_after_delete[0], True
                            else: 
                                return None, True 
                        return current_selection, False

                    if instance_name == "ollama1":
                        new_selection, changed = get_fallback_model(
                            session_data.get('selected_for_model'),
                            model_to_delete,
                            updated_models
                        )
                        if changed:
                            session_data['selected_for_model'] = new_selection
                            made_selection_change = True
                    elif instance_name == "ollama2":
                        new_selection, changed = get_fallback_model(
                            session_data.get('selected_against_model'),
                            model_to_delete,
                            updated_models
                        )
                        if changed:
                            session_data['selected_against_model'] = new_selection
                            made_selection_change = True
                    
                    if made_selection_change:
                        socketio.emit('model_selection_updated', {
                            "selected_for_model": session_data.get('selected_for_model'),
                            "selected_against_model": session_data.get('selected_against_model')
                        }, room=session_id_req)
            return jsonify({"status": "success", "message": f"Model '{model_to_delete}' delete operation processed for {instance_name}."})
        else:
            return jsonify({"status": "error", "message": f"Failed to delete model '{model_to_delete}' from {instance_name}."}), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        with long_op_lock:
            is_long_ollama_operation_active = False
        socketio.emit('long_ollama_operation_status', {"is_active": False})

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
    global is_long_ollama_operation_active
    data = request.json
    session_id = data.get('session_id')
    for_model = data.get('for_model', DEFAULT_MODEL_NAME)
    against_model = data.get('against_model', DEFAULT_MODEL_NAME)

    with long_op_lock:
        if is_long_ollama_operation_active:
            return jsonify({"status": "error", "message": "Cannot start debate: a model operation is in progress. Please wait."}), 400
    
    if not session_id or session_id not in sessions:
        return jsonify({"status": "error", "message": "Invalid session"})
    
    with session_lock:
        if not sessions[session_id]['active']:
            sessions[session_id]['active'] = True
            sessions[session_id]['selected_for_model'] = for_model
            sessions[session_id]['selected_against_model'] = against_model
            
            socketio.emit('conversation_status', {
                "active": True, 
                "is_long_ollama_operation_active": is_long_ollama_operation_active
                }, room=session_id)
            
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
            socketio.emit('conversation_status', {
                "active": False,
                "is_long_ollama_operation_active": is_long_ollama_operation_active
                }, room=session_id)
    
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
            socketio.emit('conversation_status', {
                "active": False,
                "is_long_ollama_operation_active": is_long_ollama_operation_active
                }, room=session_id)
    
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
        
        session_data['topic'] = topic
        session_data['for_position_label'] = f"For {topic}"
        session_data['against_position_label'] = f"Against {topic}"
        session_data['conversation'] = []
        
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
    flask_session_id = request.args.get('flask_session_id')
    if not flask_session_id:
        try:
            flask_session_id = session.get('session_id')
        except:
            flask_session_id = None
    
    socketio_session_id = None
    if flask_session_id:
        with session_lock:
            socketio_session_id = flask_to_socketio_map.get(flask_session_id)
    
    if socketio_session_id and socketio_session_id in sessions:
        session_id = socketio_session_id
    else:
        session_id = request.sid
        
        if flask_session_id:
            with session_lock:
                flask_to_socketio_map[flask_session_id] = session_id
        
        with session_lock:
            if session_id not in sessions:
                default_topic = "God's existence"
                sessions[session_id] = {
                    'conversation': [],
                    'active': False,
                    'topic': default_topic,
                    'for_position_label': f"For {default_topic}",
                    'against_position_label': f"Against {default_topic}",
                    'flask_session_id': flask_session_id,
                    'selected_for_model': DEFAULT_MODEL_NAME,
                    'selected_against_model': DEFAULT_MODEL_NAME
                }
    
    join_room(session_id)
    
    with session_lock:
        if session_id in sessions:  # Verify session still exists
            session_data = sessions[session_id]
            
            socketio.emit('session_init', {
                "session_id": session_id
            }, room=session_id)
            
            socketio.emit('conversation_status', {
                "active": session_data['active'],
                "is_long_ollama_operation_active": is_long_ollama_operation_active
            }, room=session_id)
            
            socketio.emit('topic_info', {
                "topic": session_data['topic'],
                "for_label": session_data['for_position_label'],
                "against_label": session_data['against_position_label']
            }, room=session_id)

            # Emit model information
            ollama1_models = list_models_in_container(OLLAMA_FOR_CONTAINER_NAME) # For LLM
            ollama2_models = list_models_in_container(OLLAMA_AGAINST_CONTAINER_NAME) # Against LLM
            socketio.emit('models_info', {
                "ollama1_models": ollama1_models, # For LLM
                "ollama2_models": ollama2_models, # Against LLM
                "pullable_models": PULLABLE_MODELS_LIST,
                "selected_for_model": session_data.get('selected_for_model', DEFAULT_MODEL_NAME),
                "selected_against_model": session_data.get('selected_against_model', DEFAULT_MODEL_NAME),
                "default_model": DEFAULT_MODEL_NAME
            }, room=session_id)
            
            if session_data['conversation']:
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
