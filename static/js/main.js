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
    let messageDelay = 0; // Used for staggered animation timing
    
    // Store active streaming messages
    let activeStreamingMessages = {};
    
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
        }
    });
    
    // Handle streaming message updates
    socket.on('stream_message', function(data) {
        const { speaker, message, message_id, done } = data;
        
        // If this is a new streaming message, create a new message element
        if (!activeStreamingMessages[message_id]) {
            // Create new message container
            const messageDiv = createMessageElement(speaker, "", message_id);
            conversation.appendChild(messageDiv);
            
            // Store reference to content span for future updates
            activeStreamingMessages[message_id] = {
                element: messageDiv,
                contentSpan: messageDiv.querySelector('.content'),
                fullText: ""
            };
            
            // Auto scroll to bottom with smooth animation
            conversation.scrollTo({
                top: conversation.scrollHeight,
                behavior: 'smooth'
            });
        }
        
        // Update the existing message with new content
        const streamingMsg = activeStreamingMessages[message_id];
        streamingMsg.fullText += message;
        streamingMsg.contentSpan.textContent = streamingMsg.fullText;
        
        // Auto scroll to keep up with the message
        conversation.scrollTo({
            top: conversation.scrollHeight,
            behavior: 'smooth'
        });
        
        // If this is the last chunk, remove from active streaming messages
        if (done) {
            delete activeStreamingMessages[message_id];
        }
    });
    
    // Handle legacy (non-streaming) new messages with staggered animation
    socket.on('new_message', function(data) {
        messageDelay += 100; // Stagger animations
        setTimeout(() => {
            addMessageToDisplay(data);
            messageDelay = 0; // Reset after a pause
        }, messageDelay);
    });
    
    function createMessageElement(speaker, initialContent, messageId) {
        const messageDiv = document.createElement('div');
        
        // Determine CSS class based on speaker
        let speakerClass = '';
        if (speaker === 'Human') {
            speakerClass = 'human';
        } else if (speaker === currentForLabel || speaker.includes('For ')) {
            speakerClass = 'for-position';
            // Ensure typing indicator is hidden when message arrives
            forTyping.classList.remove('visible');
        } else if (speaker === currentAgainstLabel || speaker.includes('Against ')) {
            speakerClass = 'against-position';
            // Ensure typing indicator is hidden when message arrives
            againstTyping.classList.remove('visible');
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
        
        messageDiv.appendChild(speakerSpan);
        messageDiv.appendChild(contentSpan);
        
        return messageDiv;
    }
    
    function addMessageToDisplay(data) {
        const messageDiv = createMessageElement(data.speaker, data.message);
        conversation.appendChild(messageDiv);
        
        // Auto scroll to bottom with smooth animation
        conversation.scrollTo({
            top: conversation.scrollHeight,
            behavior: 'smooth'
        });
    }
    
    // Update status
    socket.on('conversation_status', function(data) {
        const debateMeta = document.querySelector('.debate-meta');
        statusText.textContent = data.active ? 'Active' : 'Idle';
        statusText.className = data.active ? 'status-value active' : 'status-value';
        startBtn.disabled = data.active;
        stopBtn.disabled = !data.active;
        
        // Slide topic form up/down based on status
        if (data.active) {
            if (topicForm.style.display !== 'none') {
                topicForm.style.opacity = '0';
                setTimeout(() => {
                    topicForm.style.display = 'none';
                    // Add spacing class when topic form is hidden
                    debateMeta.classList.add('form-hidden');
                }, 300);
            }
        } else {
            topicForm.style.display = 'block';
            // Remove spacing class when topic form is visible
            debateMeta.classList.remove('form-hidden');
            setTimeout(() => {
                topicForm.style.opacity = '1';
            }, 10);
        }
        
        // Make sure typing indicators are hidden when conversation stops
        if (!data.active) {
            forTyping.classList.remove('visible');
            againstTyping.classList.remove('visible');
        }
    });
    
    // Button event listeners with visual feedback
    startBtn.addEventListener('click', function() {
        const originalText = startBtn.innerHTML;
        startBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Starting...';
        
        fetch('/api/start', { method: 'POST' })
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
        const originalText = stopBtn.innerHTML;
        stopBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Stopping...';
        
        fetch('/api/stop', { method: 'POST' })
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
        const originalText = resetBtn.innerHTML;
        resetBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Resetting...';
        
        fetch('/api/reset', { method: 'POST' })
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
    
    // Load initial conversation history with animation
    fetch('/api/conversation')
        .then(response => response.json())
        .then(data => {
            if (data.length > 0) {
                // Set short delay between messages for animation
                let delay = 0;
                data.forEach(msg => {
                    delay += 100;
                    setTimeout(() => {
                        addMessageToDisplay(msg);
                    }, delay);
                });
            }
        })
        .catch(error => console.error('Error loading conversation history:', error));
});
