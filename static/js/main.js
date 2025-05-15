document.addEventListener('DOMContentLoaded', function() {
    const socket = io();
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
    
    // Typing indicators
    const forTyping = document.getElementById('for-typing');
    const againstTyping = document.getElementById('against-typing');
    
    let currentForLabel = "For position";
    let currentAgainstLabel = "Against position";
    
    // Connect to WebSocket
    socket.on('connect', function() {
        console.log('Connected to WebSocket');
    });
    
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
    }
    
    // Handle typing indicators
    socket.on('typing_indicator', function(data) {
        const { speaker, typing } = data;
        
        if (speaker === currentForLabel || speaker.includes('For ')) {
            forTyping.classList.toggle('visible', typing);
        } else if (speaker === currentAgainstLabel || speaker.includes('Against ')) {
            againstTyping.classList.toggle('visible', typing);
        }
    });
    
    // Handle new messages
    socket.on('new_message', function(data) {
        const messageDiv = document.createElement('div');
        
        // Determine CSS class based on speaker
        let speakerClass = '';
        if (data.speaker === 'Human') {
            speakerClass = 'human';
        } else if (data.speaker === currentForLabel || data.speaker.includes('For ')) {
            speakerClass = 'for-position';
            // Ensure typing indicator is hidden when message arrives
            forTyping.classList.remove('visible');
        } else if (data.speaker === currentAgainstLabel || data.speaker.includes('Against ')) {
            speakerClass = 'against-position';
            // Ensure typing indicator is hidden when message arrives
            againstTyping.classList.remove('visible');
        } else {
            speakerClass = 'generic-llm'; // Fallback
        }
        
        messageDiv.className = `message ${speakerClass}`;
        
        const speakerSpan = document.createElement('span');
        speakerSpan.className = 'speaker';
        speakerSpan.textContent = data.speaker;
        
        const contentSpan = document.createElement('span');
        contentSpan.className = 'content';
        contentSpan.textContent = data.message;
        
        messageDiv.appendChild(speakerSpan);
        messageDiv.appendChild(contentSpan);
        conversation.appendChild(messageDiv);
        
        // Auto scroll to bottom
        conversation.scrollTop = conversation.scrollHeight;
    });
    
    // Update status
    socket.on('conversation_status', function(data) {
        statusText.textContent = data.active ? 'Active' : 'Idle';
        statusText.className = data.active ? 'status-value active' : 'status-value';
        startBtn.disabled = data.active;
        stopBtn.disabled = !data.active;
        topicForm.style.display = data.active ? 'none' : 'block';
        
        // Make sure typing indicators are hidden when conversation stops
        if (!data.active) {
            forTyping.classList.remove('visible');
            againstTyping.classList.remove('visible');
        }
    });
    
    // Button event listeners
    startBtn.addEventListener('click', function() {
        fetch('/api/start', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                console.log('Start response:', data);
                topicForm.style.display = 'none';
            })
            .catch(error => console.error('Error starting conversation:', error));
    });
    
    stopBtn.addEventListener('click', function() {
        fetch('/api/stop', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                console.log('Stop response:', data);
                topicForm.style.display = 'block';
            })
            .catch(error => console.error('Error stopping conversation:', error));
    });
    
    resetBtn.addEventListener('click', function() {
        fetch('/api/reset', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                console.log('Reset response:', data);
                conversation.innerHTML = ''; // Clear conversation display
                topicForm.style.display = 'block';
            })
            .catch(error => console.error('Error resetting conversation:', error));
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
        const topic = topicInput.value.trim();
        if (!topic) {
            alert('Please enter a topic');
            return;
        }
        
        fetch('/api/topic', { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ topic: topic })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'error') {
                alert(data.message);
            } else {
                console.log('Topic set:', data);
                // Clear any existing conversation
                conversation.innerHTML = '';
            }
        })
        .catch(error => console.error('Error setting topic:', error));
    }
    
    // Load initial conversation history
    fetch('/api/conversation')
        .then(response => response.json())
        .then(data => {
            data.forEach(msg => {
                // Use socket.on handler logic directly
                const messageDiv = document.createElement('div');
                
                // Determine CSS class based on speaker
                let speakerClass = '';
                if (msg.speaker === 'Human') {
                    speakerClass = 'human';
                } else if (msg.speaker.includes('For ')) {
                    speakerClass = 'for-position';
                } else if (msg.speaker.includes('Against ')) {
                    speakerClass = 'against-position';
                } else {
                    speakerClass = 'generic-llm'; // Fallback
                }
                
                messageDiv.className = `message ${speakerClass}`;
                
                const speakerSpan = document.createElement('span');
                speakerSpan.className = 'speaker';
                speakerSpan.textContent = msg.speaker;
                
                const contentSpan = document.createElement('span');
                contentSpan.className = 'content';
                contentSpan.textContent = msg.message;
                
                messageDiv.appendChild(speakerSpan);
                messageDiv.appendChild(contentSpan);
                conversation.appendChild(messageDiv);
            });
            
            // Auto scroll to bottom
            conversation.scrollTop = conversation.scrollHeight;
        })
        .catch(error => console.error('Error loading conversation history:', error));
});
