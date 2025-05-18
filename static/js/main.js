document.addEventListener('DOMContentLoaded', function() {
    // Get session IDs from the server
    const flaskSessionId = document.getElementById('flask-session-id')?.value;
    const serverSocketIOSessionId = document.getElementById('socketio-session-id')?.value;
    
    // Check localStorage for existing session
    const storedSocketIOSessionId = localStorage.getItem('llm_debate_socketio_id');
    
    // Determine which SocketIO session ID to use (prioritize server-provided one)
    const socketIOSessionToUse = serverSocketIOSessionId || storedSocketIOSessionId;
    
    // Initialize query parameters for connection
    const queryParams = {};
    if (flaskSessionId) {
        queryParams.flask_session_id = flaskSessionId;
    }
    if (socketIOSessionToUse) {
        queryParams.session_id = socketIOSessionToUse;
    }
    
    // Initialize socket connection with session parameters
    const socket = io({query: queryParams});
    
    const conversation = document.getElementById('conversation');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const resetBtn = document.getElementById('reset-btn');
    const statusText = document.getElementById('status-text');
    const topicForm = document.getElementById('topic-form');
    const topicInput = document.getElementById('topic-input');
    const setTopicBtn = document.getElementById('set-topic-btn');
    const debateTitle = document.getElementById('debate-title');
    const forPosition = document.getElementById('for-position');
    const againstPosition = document.getElementById('against-position');
    const maxTurnsInput = document.getElementById('max-turns-input'); // Get the new input
    
    // Typing indicators
    const forTyping = document.getElementById('for-typing');
    const againstTyping = document.getElementById('against-typing');
    const evaluatorTyping = document.createElement('div'); // Create a new typing indicator for evaluator
    evaluatorTyping.id = 'evaluator-typing';
    evaluatorTyping.className = 'typing-indicator evaluator-typing'; // Add new class
    
    const evaluatingText = document.createElement('span');
    evaluatingText.className = 'evaluating-text';
    evaluatingText.textContent = 'Evaluating';
    evaluatorTyping.appendChild(evaluatingText);
    
    evaluatorTyping.innerHTML += '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    const debateArena = document.querySelector('.debate-arena');
    if (debateArena) {
        const conversationContainer = document.getElementById('conversation');
        if (conversationContainer && conversationContainer.parentNode === debateArena) {
            debateArena.insertBefore(evaluatorTyping, conversationContainer.nextSibling);
        } else {
            debateArena.appendChild(evaluatorTyping);
        }
    }
    
    // Settings panel elements
    const settingsToggleBtn = document.getElementById('settings-toggle-btn');
    const settingsPanel = document.getElementById('settings-panel');

    // Model selection dropdowns
    const forModelSelect = document.getElementById('for-model-select');
    const againstModelSelect = document.getElementById('against-model-select');

    // Available models lists
    const ollama1AvailableModelsList = document.getElementById('ollama1-available-models');
    const ollama2AvailableModelsList = document.getElementById('ollama2-available-models');

    // Pull model options containers
    const ollama1PullOptions = document.getElementById('ollama1-pull-options');
    const ollama2PullOptions = document.getElementById('ollama2-pull-options');
    
    // Pull status text
    const ollama1PullStatus = document.getElementById('ollama1-pull-status');
    const ollama2PullStatus = document.getElementById('ollama2-pull-status');

    let currentPullableModels = [];
    let currentDefaultModel = "";
    let isDebateActive = false; // Track debate status locally
    let isGloballyOperatingOllama = false; // Renamed from isGloballyPullingModel

    // Session management
    let sessionId = null;
    let isInitialLoad = true;
    let currentForLabel = "For position";
    let currentAgainstLabel = "Against position";
    let messageDelay = 0; // Used for staggered animation timing
    
    // Store active streaming messages
    let activeStreamingMessages = {};
    
    // Track if user is scrolled to bottom
    let isNearBottom = true;
    
    // Check if the conversation container is scrolled to the bottom
    function isScrolledNearBottom() {
        const threshold = 100; // pixels from bottom to consider "at bottom"
        return conversation.scrollHeight - conversation.clientHeight - conversation.scrollTop <= threshold;
    }
    
    // Smart scroll that only auto-scrolls if already near the bottom
    function smartScroll() {
        if (isNearBottom) {
            conversation.scrollTo({
                top: conversation.scrollHeight,
                behavior: 'smooth'
            });
        }
    }
    
    // Listen for user scrolling to track position
    conversation.addEventListener('scroll', function() {
        isNearBottom = isScrolledNearBottom();
    });
    
    // Connect to WebSocket
    socket.on('connect', function() {
        console.log('Connected to WebSocket');
        // Session will be initialized by the server
    });
    
    // Receive session ID from server and store it
    socket.on('session_init', function(data) {
        sessionId = data.session_id;
        console.log('Session initialized:', sessionId);
        
        // Store session ID in localStorage for persistence
        localStorage.setItem('llm_debate_socketio_id', sessionId);
        
        if (data.max_turns !== undefined) {
            maxTurnsInput.value = data.max_turns;
        }
        // Don't automatically load history since we'll get it from the server
        isInitialLoad = false;
    });
    
    // Handle receiving conversation history (for refreshed sessions)
    socket.on('conversation_history', function(data) {
        if (data.messages && data.messages.length > 0) {
            // Clear existing conversation first to prevent duplicates
            conversation.innerHTML = '';
            
            console.log('Restoring conversation history, messages:', data.messages.length);
            
            // Ensure proper message ordering by creating an array of delayed functions
            const messageFunctions = [];
            
            // Create a function for each message with its own delay
            data.messages.forEach((msg, index) => {
                const delay = index * 50;  // Faster animation for restored messages
                messageFunctions.push({
                    func: () => addMessageToDisplay(msg),
                    delay: delay,
                    index: index
                });
            });
            
            // Execute all message functions in order
            messageFunctions.forEach((item) => {
                setTimeout(() => {
                    item.func();
                    // Scroll to bottom after all messages are added
                    if (item.index === data.messages.length - 1) {
                        isNearBottom = true;
                        smartScroll();
                    }
                }, item.delay);
            });
        }
    });
    
    // Load conversation history from the server
    function loadConversationHistory() {
        if (!sessionId) return;
        
        fetch(`/api/conversation?session_id=${sessionId}`)
            .then(response => response.json())
            .then(data => {
                if (data.length > 0) {
                    // Clear existing messages first to prevent duplicates
                    conversation.innerHTML = '';
                    
                    // Set short delay between messages for animation
                    let delay = 0;
                    data.forEach((msg, index) => {
                        delay += 100;
                        setTimeout(() => {
                            addMessageToDisplay(msg);
                            // If this is the last message, ensure we're scrolled to the bottom
                            if (index === data.length - 1) {
                                isNearBottom = true; // Force scroll to bottom after loading history
                                smartScroll();
                            }
                        }, delay);
                    });
                }
            })
            .catch(error => console.error('Error loading conversation history:', error));
    }
    
    // Handle topic updates
    socket.on('topic_updated', function(data) {
        updateTopicDisplay(data.topic, data.for_label, data.against_label);
    });
    
    socket.on('topic_info', function(data) {
        updateTopicDisplay(data.topic, data.for_label, data.against_label);
    });
    
    function updateTopicDisplay(topic, forLabel, againstLabel) {
        debateTitle.textContent = `LLM Debate: ${topic}`;
        document.title = `LLM Debate: ${topic}`;
        forPosition.textContent = forLabel;
        againstPosition.textContent = againstLabel;
        currentForLabel = forLabel;
        currentAgainstLabel = againstLabel;
        
        // Add a subtle highlight effect to the title
        debateTitle.classList.add('highlight');
        setTimeout(() => debateTitle.classList.remove('highlight'), 1000);
    }
    
    // Handle typing indicators
    socket.on('typing_indicator', function(data) {
        const { speaker, typing } = data;
        
        if (speaker === currentForLabel || speaker.includes('For ')) {
            forTyping.classList.toggle('visible', typing);
        } else if (speaker === currentAgainstLabel || speaker.includes('Against ')) {
            againstTyping.classList.toggle('visible', typing);
        } else if (speaker === 'Evaluator') {
            evaluatorTyping.classList.toggle('visible', typing);
        }
    });
    
    // Handle streaming message updates
    socket.on('stream_message', function(data) {
        const { speaker, message: chunk_text, message_id, done } = data;
        let msgData = activeStreamingMessages[message_id];
    
        if (!msgData) {
            isNearBottom = isScrolledNearBottom();
            const messageDiv = createMessageElement(speaker, "", message_id);
            conversation.appendChild(messageDiv);
            
            msgData = {
                element: messageDiv,
                contentSpan: messageDiv.querySelector('.content'),
                thinkingSpan: messageDiv.querySelector('.thinking-indicator-inline'),
                isCurrentlyThinking: false,
                fullText: "" // Stores only the actual response text to be displayed
            };
            activeStreamingMessages[message_id] = msgData;
            smartScroll();
        }
    
        let processText = chunk_text;
    
        while (processText.length > 0) {
            if (msgData.isCurrentlyThinking) {
                const thinkEndIndex = processText.indexOf('</think>');
                if (thinkEndIndex !== -1) {
                    msgData.isCurrentlyThinking = false;
                    msgData.thinkingSpan.style.display = 'none';
                    processText = processText.substring(thinkEndIndex + '</think>'.length);
                } else {
                    processText = ""; // Consume the rest of this chunk's thought
                }
            } else { // Not currently thinking
                const thinkStartIndex = processText.indexOf('<think>');
                if (thinkStartIndex !== -1) {
                    const regularText = processText.substring(0, thinkStartIndex);
                    if (regularText.length > 0) {
                        msgData.fullText += regularText;
                        msgData.contentSpan.textContent = msgData.fullText;
                    }
    
                    msgData.isCurrentlyThinking = true;
                    msgData.thinkingSpan.style.display = 'inline-flex'; // Show thinking indicator
                    processText = processText.substring(thinkStartIndex + '<think>'.length);
                } else {
                    if (processText.length > 0) {
                        msgData.fullText += processText;
                        msgData.contentSpan.textContent = msgData.fullText;
                    }
                    processText = "";
                }
            }
        }
        
        if (!msgData.isCurrentlyThinking) {
            msgData.contentSpan.style.display = 'inline';
        }

        smartScroll();
    
        if (done) {
            if (msgData.isCurrentlyThinking) { // If stream ends mid-thought
                msgData.thinkingSpan.style.display = 'none';
                msgData.contentSpan.style.display = 'inline';
            }
            msgData.contentSpan.textContent = msgData.fullText; 
            delete activeStreamingMessages[message_id];
        }
    });
    
    function createMessageElement(speaker, initialContent, messageId) {
        const messageDiv = document.createElement('div');
        
        // Determine CSS class based on speaker
        let speakerClass = '';
        if (speaker === 'Human') {
            speakerClass = 'human';
        } else if (speaker === currentForLabel || speaker.includes('For ')) {
            speakerClass = 'for-position';
            forTyping.classList.remove('visible');
        } else if (speaker === currentAgainstLabel || speaker.includes('Against ')) {
            speakerClass = 'against-position';
            againstTyping.classList.remove('visible');
        } else if (speaker === 'Evaluator') {
            speakerClass = 'evaluator-message';
            evaluatorTyping.classList.remove('visible');
        } else if (speaker === 'System') {
            speakerClass = 'system-message';
        } else {
            speakerClass = 'generic-llm'; // Fallback
        }
        
        messageDiv.className = `message ${speakerClass}`;
        messageDiv.style.animationDelay = `${messageDelay}ms`;
        if (messageId) {
            messageDiv.dataset.messageId = messageId;
        }
        
        const speakerSpan = document.createElement('span');
        speakerSpan.className = 'speaker';
        speakerSpan.textContent = speaker;
        
        const contentSpan = document.createElement('span');
        contentSpan.className = 'content';
        contentSpan.textContent = initialContent;

        const thinkingSpan = document.createElement('span');
        thinkingSpan.className = 'thinking-indicator-inline'; // New class for inline thinking
        thinkingSpan.style.display = 'none'; // Hidden by default
        
        const thinkingText = document.createTextNode('Thinking'); // Add "Thinking" text
        thinkingSpan.appendChild(thinkingText);

        const dot1 = document.createElement('span'); dot1.className = 'dot';
        const dot2 = document.createElement('span'); dot2.className = 'dot';
        const dot3 = document.createElement('span'); dot3.className = 'dot';
        thinkingSpan.append(dot1, dot2, dot3);
        
        messageDiv.appendChild(speakerSpan);
        messageDiv.appendChild(contentSpan);
        messageDiv.appendChild(thinkingSpan); // Add the thinking indicator
        
        return messageDiv;
    }
    
    function addMessageToDisplay(data) {
        const messageDiv = createMessageElement(data.speaker, data.message);
        conversation.appendChild(messageDiv);
        
        // Smart scroll for new messages
        smartScroll();
    }
    
    // Update status with proper UI state restoration
    socket.on('conversation_status', function(data) {
        const debateMeta = document.querySelector('.debate-meta');
        statusText.textContent = data.active ? 'Active' : 'Idle';
        statusText.className = data.active ? 'status-value active' : 'status-value';
        
        isDebateActive = data.active;
        isGloballyOperatingOllama = data.is_long_ollama_operation_active || false; // Update global op status

        updateGlobalControlsState(); // Central function to manage UI element states

        startBtn.disabled = data.active;
        stopBtn.disabled = !data.active;
        
        // Slide topic form up/down based on status - ensure proper state after refresh
        if (data.active) {
            topicForm.style.display = 'none';
            topicForm.style.opacity = '0';
            debateMeta.classList.add('form-hidden');
        } else {
            topicForm.style.display = 'block';
            topicForm.style.opacity = '1';
            debateMeta.classList.remove('form-hidden');
        }
        
        // Make sure typing indicators are hidden when conversation stops
        if (!data.active) {
            forTyping.classList.remove('visible');
            againstTyping.classList.remove('visible');
            evaluatorTyping.classList.remove('visible'); // Hide evaluator typing too
        }
    });

    // Handle global model operation status updates
    socket.on('long_ollama_operation_status', function(data) { // Renamed event
        isGloballyOperatingOllama = data.is_active; // Renamed property
        updateGlobalControlsState();
        
        if (!isGloballyOperatingOllama) {
            [ollama1PullStatus, ollama2PullStatus].forEach(el => {
                if (el.textContent.includes("Pulling") || el.textContent.includes("Deleting")) { 
                    el.textContent = 'Ollama operation finished.';
                    setTimeout(() => { if(el.textContent === 'Ollama operation finished.') el.textContent = ''; }, 3000);
                }
            });
        }
    });

    socket.on('model_selection_updated', function(data) {
        console.log('Received model_selection_updated:', data);
        if (data.selected_for_model) {
            forModelSelect.value = data.selected_for_model;
        }
        if (data.selected_against_model) {
            againstModelSelect.value = data.selected_against_model;
        }
    });
    
    function updateGlobalControlsState() {
        const debateCanStart = !isDebateActive && !isGloballyOperatingOllama;
        startBtn.disabled = !debateCanStart;
        stopBtn.disabled = !isDebateActive; // Stop only if active

        // Settings panel and its contents
        const settingsAreEditable = !isDebateActive && !isGloballyOperatingOllama;
        settingsToggleBtn.disabled = isDebateActive; // Disable settings toggle if debate active

        [forModelSelect, againstModelSelect, maxTurnsInput].forEach(select => { // Add maxTurnsInput here
            select.disabled = !settingsAreEditable;
        });

        document.querySelectorAll('.pull-options-list button, .delete-model-btn').forEach(btn => {
            btn.disabled = !settingsAreEditable;
        });
        
        // If settings panel is open and debate starts, or pull starts, visually disable it
        if (settingsPanel.style.display === 'block' && !settingsAreEditable) {
            // Optionally add a class to grey out settings or just rely on disabled inputs
            settingsPanel.classList.add('panel-disabled');
        } else {
            settingsPanel.classList.remove('panel-disabled');
        }
    }

    // Toggle settings panel
    if (settingsToggleBtn && settingsPanel) {
        settingsToggleBtn.addEventListener('click', function() {
            if (isDebateActive) return; // Prevent opening if debate is active

            if (settingsPanel.style.display === 'none') {
                settingsPanel.style.display = 'block';
                // Optionally, fetch model info when panel is opened if not already fresh
                // fetchModelInfoForAllInstances(); // You might want to implement this
            } else {
                settingsPanel.style.display = 'none';
            }
        });
    }

    function updateAvailableModelsList(listElement, models, selectedModel, selectElement, instanceName) {
        listElement.innerHTML = '';
        selectElement.innerHTML = ''; // Clear select options too

        if (models && models.length > 0) {
            models.forEach(model => {
                const li = document.createElement('li');
                li.className = 'list-group-item d-flex justify-content-between align-items-center';
                
                const modelNameSpan = document.createElement('span');
                modelNameSpan.textContent = model;
                li.appendChild(modelNameSpan);

                const controlsDiv = document.createElement('div');

                if (model === currentDefaultModel) {
                    const badge = document.createElement('span');
                    badge.className = 'badge bg-info rounded-pill me-2';
                    badge.textContent = 'Default';
                    controlsDiv.appendChild(badge);
                } else {
                    // Only add delete button if it's NOT the default model
                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'btn btn-sm btn-outline-danger delete-model-btn';
                    deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
                    deleteBtn.title = `Delete ${model}`;
                    deleteBtn.onclick = (e) => {
                        e.stopPropagation(); // Prevent li click if any
                        if (confirm(`Are you sure you want to delete model "${model}" from ${instanceName === 'ollama1' ? 'For LLM' : 'Against LLM'}?`)) {
                            deleteModel(instanceName, model);
                        }
                    };
                    controlsDiv.appendChild(deleteBtn);
                }
                
                // Append controlsDiv only if it has children (either badge or button)
                if (controlsDiv.hasChildNodes()) {
                    li.appendChild(controlsDiv);
                }
                listElement.appendChild(li);

                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                if (model === selectedModel) {
                    option.selected = true;
                }
                selectElement.appendChild(option);
            });
        } else {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.textContent = 'No models available. Pull one below.';
            listElement.appendChild(li);
            const option = document.createElement('option');
            option.textContent = 'No models available';
            option.disabled = true;
            selectElement.appendChild(option);
        }
    }

    function populatePullOptions(containerElement, instanceName, availableModels) {
        containerElement.innerHTML = '';
        currentPullableModels.forEach(modelToPull => {
            if (!availableModels.includes(modelToPull)) { // Only show pull option if not already available
                const btn = document.createElement('button');
                btn.className = 'btn btn-sm btn-outline-secondary me-1 mb-1';
                btn.innerHTML = `<i class="bi bi-download me-1"></i> ${modelToPull}`;
                btn.onclick = () => pullModel(instanceName, modelToPull);
                containerElement.appendChild(btn);
            }
        });
        updateGlobalControlsState(); // Ensure new buttons get correct disabled state
    }

    function pullModel(instanceName, modelName) {
        if (isDebateActive || isGloballyOperatingOllama) {
            alert("Cannot pull model now. A debate is active or another Ollama operation is in progress.");
            return;
        }

        const statusElement = instanceName === 'ollama1' ? ollama1PullStatus : ollama2PullStatus;
        statusElement.innerHTML = `<i class="bi bi-hourglass-split me-1"></i>Pulling ${modelName}... This can take a while.`;
        statusElement.className = 'pull-status-text text-info';
        
        // Disable all pull buttons globally and start button
        isGloballyOperatingOllama = true; // Optimistically set, backend will confirm
        updateGlobalControlsState();

        const pullOptionsContainer = instanceName === 'ollama1' ? ollama1PullOptions : ollama2PullOptions;
        pullOptionsContainer.querySelectorAll('button').forEach(btn => btn.disabled = true);

        fetch('/api/pull_model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ instance_name: instanceName, model_name: modelName, session_id: sessionId })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                statusElement.textContent = data.message;
                statusElement.className = 'pull-status-text text-success';
                // Backend will emit 'models_updated' which will refresh the lists
            } else {
                statusElement.textContent = `Error: ${data.message}`;
                statusElement.className = 'pull-status-text text-danger';
            }
        })
        .catch(error => {
            statusElement.textContent = `Fetch error: ${error}`;
            statusElement.className = 'pull-status-text text-danger';
            isGloballyOperatingOllama = false; 
            updateGlobalControlsState();
        });
    }

    function deleteModel(instanceName, modelName) {
        if (isDebateActive || isGloballyOperatingOllama) {
            alert("Cannot delete model now. A debate is active or another Ollama operation is in progress.");
            return;
        }

        const statusElement = instanceName === 'ollama1' ? ollama1PullStatus : ollama2PullStatus;
        statusElement.innerHTML = `<i class="bi bi-hourglass-split me-1"></i>Deleting ${modelName}...`;
        statusElement.className = 'pull-status-text text-info';

        isGloballyOperatingOllama = true;
        updateGlobalControlsState();

        fetch('/api/delete_model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ instance_name: instanceName, model_name: modelName, session_id: sessionId })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' || data.status === 'info') {
                statusElement.textContent = data.message;
                statusElement.className = data.status === 'success' ? 'pull-status-text text-success' : 'pull-status-text text-warning';
                // Backend emits 'models_updated'
            } else {
                statusElement.textContent = `Error: ${data.message}`;
                statusElement.className = 'pull-status-text text-danger';
            }
        })
        .catch(error => {
            statusElement.textContent = `Fetch error: ${error}`;
            statusElement.className = 'pull-status-text text-danger';
            isGloballyOperatingOllama = false;
            updateGlobalControlsState();
        });
        // Backend will set isGloballyOperatingOllama to false and emit status
    }

    socket.on('models_info', function(data) {
        console.log('Received models_info:', data);
        currentPullableModels = data.pullable_models || [];
        currentDefaultModel = data.default_model || "gemma3:4b"; // Ensure this matches DEFAULT_MODEL_NAME in app.py
        if (data.max_turns !== undefined) {
            maxTurnsInput.value = data.max_turns;
        }

        // ollama1 is "For LLM"
        updateAvailableModelsList(ollama1AvailableModelsList, data.ollama1_models, data.selected_for_model, forModelSelect, 'ollama1');
        populatePullOptions(ollama1PullOptions, 'ollama1', data.ollama1_models || []);
        
        // ollama2 is "Against LLM"
        updateAvailableModelsList(ollama2AvailableModelsList, data.ollama2_models, data.selected_against_model, againstModelSelect, 'ollama2');
        populatePullOptions(ollama2PullOptions, 'ollama2', data.ollama2_models || []);
        
        updateGlobalControlsState(); // Apply initial state to controls
    });

    socket.on('models_updated', function(data) {
        console.log('Received models_updated:', data);
        const { instance_name, models } = data;
        let statusElement, listElement, selectElement, pullOptionsContainer, currentSelectedModel;

        if (instance_name === 'ollama1') {
            statusElement = ollama1PullStatus;
            listElement = ollama1AvailableModelsList;
            selectElement = forModelSelect;
            pullOptionsContainer = ollama1PullOptions;
            currentSelectedModel = forModelSelect.value; // Preserve current selection if possible
        } else if (instance_name === 'ollama2') {
            statusElement = ollama2PullStatus;
            listElement = ollama2AvailableModelsList;
            selectElement = againstModelSelect;
            pullOptionsContainer = ollama2PullOptions;
            currentSelectedModel = againstModelSelect.value; // Preserve current selection
        } else {
            return;
        }
        
        updateAvailableModelsList(listElement, models, currentSelectedModel, selectElement, instance_name);
        populatePullOptions(pullOptionsContainer, instance_name, models || []);
        updateGlobalControlsState(); // Re-apply disabled states after list update
    });

    // Button event listeners with visual feedback
    startBtn.addEventListener('click', function() {
        if (!sessionId || isDebateActive || isGloballyOperatingOllama) return;
        
        const originalText = startBtn.innerHTML;
        startBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Starting...';

        const selectedForModel = forModelSelect.value;
        const selectedAgainstModel = againstModelSelect.value;
        const numExchanges = parseInt(maxTurnsInput.value, 10);

        if (!selectedForModel || !selectedAgainstModel) {
            alert("Please select models for both 'For' and 'Against' positions in the Settings panel.");
            startBtn.innerHTML = originalText;
            return;
        }
        if (isNaN(numExchanges) || numExchanges < 1 || numExchanges > 5) {
            alert("Please enter a valid number of exchanges (1-5).");
            maxTurnsInput.focus();
            startBtn.innerHTML = originalText;
            return;
        }
        
        fetch('/api/start', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                session_id: sessionId,
                for_model: selectedForModel,
                against_model: selectedAgainstModel,
                max_turns: numExchanges // Send max_turns
            })
        })
            .then(response => response.json())
            .then(data => {
                console.log('Start response:', data);
                startBtn.innerHTML = originalText;
            })
            .catch(error => {
                console.error('Error starting conversation:', error);
                startBtn.innerHTML = originalText;
            });
    });
    
    stopBtn.addEventListener('click', function() {
        if (!sessionId) return;
        
        const originalText = stopBtn.innerHTML;
        stopBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Stopping...';
        
        fetch('/api/stop', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        })
            .then(response => response.json())
            .then(data => {
                console.log('Stop response:', data);
                stopBtn.innerHTML = originalText;
            })
            .catch(error => {
                console.error('Error stopping conversation:', error);
                stopBtn.innerHTML = originalText;
            });
    });
    
    resetBtn.addEventListener('click', function() {
        if (!sessionId) return;
        
        const originalText = resetBtn.innerHTML;
        resetBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Resetting...';
        
        fetch('/api/reset', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        })
            .then(response => response.json())
            .then(data => {
                console.log('Reset response:', data);
                conversation.innerHTML = ''; // Clear conversation display
                resetBtn.innerHTML = originalText;
            })
            .catch(error => {
                console.error('Error resetting conversation:', error);
                resetBtn.innerHTML = originalText;
            });
    });
    
    // Topic form submission
    setTopicBtn.addEventListener('click', function() {
        setDebateTopic();
    });
    
    // Also submit when pressing Enter in the input field
    topicInput.addEventListener('keyup', function(event) {
        if (event.key === 'Enter') {
            setDebateTopic();
        }
    });
    
    function setDebateTopic() {
        if (!sessionId) return;
        
        const topic = topicInput.value.trim();
        if (!topic) {
            // Add validation style
            topicInput.classList.add('is-invalid');
            setTimeout(() => topicInput.classList.remove('is-invalid'), 3000);
            return;
        }
        
        const originalText = setTopicBtn.innerHTML;
        setTopicBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Setting...';
        setTopicBtn.disabled = true;
        
        fetch('/api/topic', { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                topic: topic,
                session_id: sessionId
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'error') {
                alert(data.message);
            } else {
                console.log('Topic set:', data);
                // Clear any existing conversation
                conversation.innerHTML = '';
                topicInput.value = '';
            }
            setTopicBtn.innerHTML = originalText;
            setTopicBtn.disabled = false;
        })
        .catch(error => {
            console.error('Error setting topic:', error);
            setTopicBtn.innerHTML = originalText;
            setTopicBtn.disabled = false;
        });
    }
    
    // Handle window visibility changes to properly reconnect if needed
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible' && sessionId) {
            // When tab becomes visible again, check if we need to refresh the data
            console.log("Tab visible again, checking connection status");
            if (!socket.connected) {
                console.log("Socket disconnected, attempting to reconnect");
                socket.connect();
            }
        }
    });
});
