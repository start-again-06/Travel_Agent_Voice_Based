/**
 * Voice Travel Agent - Frontend Client
 * Handles voice recording, WebSocket communication, and audio playback
 */

class VoiceAgent {
    constructor() {
        this.websocket = null;
        this.mediaRecorder = null;
        this.audioContext = null;
        this.audioQueue = [];
        this.currentAudioChunks = []; // Buffer for accumulating MP3 chunks
        this.currentAudio = null; // Current HTML5 Audio element
        this.isPlaying = false;
        this.isRecording = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;

        // UI elements
        this.recordBtn = document.getElementById('recordBtn');
        this.stopBtn = document.getElementById('stopBtn');
        this.transcriptEl = document.getElementById('transcript');
        this.statusEl = document.getElementById('status');
        this.connectionStatusEl = document.getElementById('connectionStatus');
        this.clearTranscriptBtn = document.getElementById('clearTranscript');
        this.itineraryContainer = document.getElementById('itineraryContainer');
        this.itineraryContent = document.getElementById('itineraryContent');
        this.closeItineraryBtn = document.getElementById('closeItinerary');

        // Email UI elements
        this.emailItineraryBtn = document.getElementById('emailItineraryBtn');
        this.emailModal = document.getElementById('emailModal');
        this.closeEmailModal = document.getElementById('closeEmailModal');
        this.cancelEmail = document.getElementById('cancelEmail');
        this.sendEmail = document.getElementById('sendEmail');
        this.emailInput = document.getElementById('emailInput');
        this.emailError = document.getElementById('emailError');
        this.emailSuccess = document.getElementById('emailSuccess');
        this.successText = document.getElementById('successText');

        // Store current itinerary data
        this.currentDestination = '';
        this.currentItinerary = '';

        this.init();
    }

    init() {
        // Set up event listeners
        this.recordBtn.addEventListener('click', () => this.startRecording());
        this.stopBtn.addEventListener('click', () => this.stopRecording());
        this.clearTranscriptBtn.addEventListener('click', () => this.clearTranscript());
        this.closeItineraryBtn.addEventListener('click', () => this.closeItinerary());

        // Email event listeners
        this.emailItineraryBtn.addEventListener('click', () => this.openEmailModal());
        this.closeEmailModal.addEventListener('click', () => this.closeEmailModalHandler());
        this.cancelEmail.addEventListener('click', () => this.closeEmailModalHandler());
        this.sendEmail.addEventListener('click', () => this.sendItineraryEmail());

        // Close modal when clicking outside
        this.emailModal.addEventListener('click', (e) => {
            if (e.target === this.emailModal) {
                this.closeEmailModalHandler();
            }
        });

        // Handle Enter key in email input
        this.emailInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.sendItineraryEmail();
            }
        });

        // Connect to WebSocket
        this.connectWebSocket();

        // Initialize audio context (on user interaction for browsers)
        document.addEventListener('click', () => {
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
        }, { once: true });
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/voice`;

        this.updateConnectionStatus('connecting', 'Connecting to server...');

        try {
            this.websocket = new WebSocket(wsUrl);

            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.updateConnectionStatus('connected', 'Connected');
                this.reconnectAttempts = 0;

                // Hide connection status after 2 seconds
                setTimeout(() => {
                    this.connectionStatusEl.style.display = 'none';
                }, 2000);
            };

            this.websocket.onmessage = (event) => {
                const message = JSON.parse(event.data);
                this.handleServerMessage(message);
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateConnectionStatus('error', 'Connection error');
            };

            this.websocket.onclose = () => {
                console.log('WebSocket disconnected');
                this.updateConnectionStatus('disconnected', 'Disconnected');
                this.attemptReconnect();
            };

        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.updateConnectionStatus('error', 'Connection failed');
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);

            this.updateConnectionStatus('reconnecting', `Reconnecting in ${delay/1000}s...`);

            setTimeout(() => {
                console.log(`Reconnect attempt ${this.reconnectAttempts}`);
                this.connectWebSocket();
            }, delay);
        } else {
            this.updateConnectionStatus('error', 'Connection failed. Please refresh the page.');
        }
    }

    updateConnectionStatus(state, message) {
        this.connectionStatusEl.style.display = 'flex';
        const indicator = this.connectionStatusEl.querySelector('.connection-indicator');
        indicator.className = `connection-indicator ${state}`;
        this.connectionStatusEl.querySelector('span:last-child').textContent = message;
    }

    async startRecording() {
        if (this.isRecording) return;

        try {
            // Request microphone access
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            // Buffer to collect all audio chunks
            this.recordedChunks = [];

            // Create media recorder
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    // Collect chunks locally - don't send yet
                    this.recordedChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = async () => {
                // Stop all tracks
                stream.getTracks().forEach(track => track.stop());

                // Create complete audio blob from all chunks
                const completeAudioBlob = new Blob(this.recordedChunks, {
                    type: 'audio/webm;codecs=opus'
                });

                console.log(`Recorded complete audio: ${completeAudioBlob.size} bytes from ${this.recordedChunks.length} chunks`);

                // Convert complete blob to base64 and send once
                if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                    const reader = new FileReader();
                    reader.onloadend = () => {
                        const base64 = reader.result.split(',')[1];

                        // Send single complete audio file
                        this.websocket.send(JSON.stringify({
                            type: 'audio_chunk',
                            data: base64
                        }));

                        // Send stop recording signal
                        this.websocket.send(JSON.stringify({
                            type: 'stop_recording',
                            timestamp: new Date().toISOString()
                        }));

                        console.log('Sent complete audio to server');
                    };
                    reader.readAsDataURL(completeAudioBlob);
                }

                // Clear chunks
                this.recordedChunks = [];
            };

            // Start recording - collect all data into one chunk
            this.mediaRecorder.start();
            this.isRecording = true;

            // Update UI
            this.updateStatus('recording', 'Listening...');
            this.recordBtn.disabled = true;
            this.stopBtn.disabled = false;

        } catch (error) {
            console.error('Error accessing microphone:', error);
            alert('Microphone access is required. Please allow microphone access and try again.');
            this.updateStatus('error', 'Microphone access denied');
        }
    }

    stopRecording() {
        if (!this.isRecording || !this.mediaRecorder) return;

        this.mediaRecorder.stop();
        this.isRecording = false;

        // Update UI - signal sent in onstop handler
        this.updateStatus('processing', 'Processing...');
        this.recordBtn.disabled = false;
        this.stopBtn.disabled = true;
    }

    handleServerMessage(message) {
        console.log('Received message:', message.type);

        switch (message.type) {
            case 'transcript':
                this.addTranscript(message.source, message.text, message.is_final);
                // Start fresh audio buffer for agent responses
                if (message.source === 'agent') {
                    this.currentAudioChunks = [];
                }
                break;

            case 'audio_chunk':
                this.bufferAudioChunk(message.data);
                break;

            case 'itinerary_display':
                this.displayItinerary(message.content);
                break;

            case 'agent_thinking':
                this.addThinking(message.message);
                break;

            case 'agent_complete':
                this.playBufferedAudio();
                this.updateStatus('idle', 'Ready to listen');
                break;

            case 'error':
                this.addError(message.message);
                this.updateStatus('error', 'Error occurred');
                break;

            case 'agent_interrupted':
                this.currentAudioChunks = [];
                this.updateStatus('idle', 'Interrupted - Ready to listen');
                break;

            default:
                console.warn('Unknown message type:', message.type);
        }
    }

    addTranscript(source, text, isFinal) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${source}-message${!isFinal ? ' partial' : ''}`;

        const icon = source === 'user' ? '👤' : '🤖';
        const label = source === 'user' ? 'You' : 'Agent';

        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="message-icon">${icon}</span>
                <span class="message-label">${label}</span>
            </div>
            <div class="message-text">${text}</div>
        `;

        this.transcriptEl.appendChild(messageDiv);
        this.scrollToBottom();
    }

    addThinking(message) {
        const thinkingDiv = document.createElement('div');
        thinkingDiv.className = 'message thinking-message';
        thinkingDiv.innerHTML = `
            <span class="message-icon">⏳</span>
            <span class="message-text">${message}</span>
        `;

        this.transcriptEl.appendChild(thinkingDiv);
        this.scrollToBottom();

        // Remove thinking message after a short delay if not removed by next message
        setTimeout(() => {
            if (thinkingDiv.parentNode) {
                thinkingDiv.remove();
            }
        }, 10000);
    }

    addError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'message error-message';
        errorDiv.innerHTML = `
            <span class="message-icon">⚠️</span>
            <span class="message-text">${message}</span>
        `;

        this.transcriptEl.appendChild(errorDiv);
        this.scrollToBottom();
    }

    bufferAudioChunk(base64Audio) {
        try {
            // Decode base64 to binary data
            const binaryString = atob(base64Audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // Accumulate chunks
            this.currentAudioChunks.push(bytes);
            console.log(`Buffered audio chunk ${this.currentAudioChunks.length}`);
        } catch (error) {
            console.error('Error buffering audio chunk:', error);
        }
    }

    playBufferedAudio() {
        if (this.currentAudioChunks.length === 0) {
            console.log('No audio chunks to play');
            return;
        }

        try {
            // Combine all chunks into a single Uint8Array
            const totalLength = this.currentAudioChunks.reduce((sum, chunk) => sum + chunk.length, 0);
            const completeAudio = new Uint8Array(totalLength);

            let offset = 0;
            for (const chunk of this.currentAudioChunks) {
                completeAudio.set(chunk, offset);
                offset += chunk.length;
            }

            // Create a Blob from the complete audio data
            const audioBlob = new Blob([completeAudio], { type: 'audio/mpeg' });
            const audioUrl = URL.createObjectURL(audioBlob);

            // Stop any currently playing audio
            if (this.currentAudio) {
                this.currentAudio.pause();
                URL.revokeObjectURL(this.currentAudio.src);
            }

            // Create and play the audio
            this.currentAudio = new Audio(audioUrl);
            this.currentAudio.onended = () => {
                URL.revokeObjectURL(audioUrl);
                console.log('Audio playback completed');
            };
            this.currentAudio.onerror = (error) => {
                console.error('Audio playback error:', error);
                URL.revokeObjectURL(audioUrl);
            };

            this.currentAudio.play().catch(error => {
                console.error('Error playing audio:', error);
            });

            console.log(`Playing complete audio (${this.currentAudioChunks.length} chunks, ${totalLength} bytes)`);

            // Clear the buffer
            this.currentAudioChunks = [];

        } catch (error) {
            console.error('Error playing buffered audio:', error);
        }
    }

    updateStatus(state, message) {
        const indicator = this.statusEl.querySelector('.status-indicator');
        const text = this.statusEl.querySelector('.status-text');

        indicator.className = `status-indicator ${state}`;
        text.textContent = message;
    }

    clearTranscript() {
        this.transcriptEl.innerHTML = `
            <div class="message system-message">
                <span class="message-icon">ℹ️</span>
                <span class="message-text">Transcript cleared. Click the microphone to start speaking...</span>
            </div>
        `;
    }

    displayItinerary(markdownContent) {
        // Store itinerary for email functionality
        this.currentItinerary = markdownContent;

        // Extract destination from first heading
        const destinationMatch = markdownContent.match(/^# (.+)$/m) || markdownContent.match(/Day \d+:.*?-\s*(.+?)$/m);
        if (destinationMatch) {
            this.currentDestination = destinationMatch[1].trim();
        } else {
            this.currentDestination = 'Your Trip';
        }

        // Convert markdown to HTML (simple implementation)
        let html = markdownContent
            .replace(/^# (.+)$/gm, '<h2>$1</h2>')
            .replace(/^\* (.+)$/gm, '<li>$1</li>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n\n/g, '</ul><p>')
            .replace(/<li>/g, '<ul><li>')
            .replace(/<\/li>\n(?!<li>)/g, '</li></ul>');

        this.itineraryContent.innerHTML = html;
        this.itineraryContainer.style.display = 'block';
        console.log('Displayed itinerary in separate panel');
    }

    closeItinerary() {
        this.itineraryContainer.style.display = 'none';
    }

    scrollToBottom() {
        this.transcriptEl.scrollTop = this.transcriptEl.scrollHeight;
    }

    // Email functionality
    openEmailModal() {
        if (!this.currentItinerary) {
            alert('No itinerary to send. Please generate an itinerary first.');
            return;
        }

        // Reset modal state
        this.emailInput.value = '';
        this.emailError.style.display = 'none';
        this.emailSuccess.style.display = 'none';
        this.sendEmail.disabled = false;

        // Show modal
        this.emailModal.style.display = 'flex';
        this.emailInput.focus();
    }

    closeEmailModalHandler() {
        this.emailModal.style.display = 'none';
    }

    validateEmail(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    }

    async sendItineraryEmail() {
        const email = this.emailInput.value.trim();

        // Reset error state
        this.emailError.style.display = 'none';

        // Validate email
        if (!email) {
            this.emailError.textContent = 'Please enter an email address';
            this.emailError.style.display = 'block';
            return;
        }

        if (!this.validateEmail(email)) {
            this.emailError.textContent = 'Please enter a valid email address';
            this.emailError.style.display = 'block';
            return;
        }

        // Disable button and show loading
        this.sendEmail.disabled = true;
        const spinner = this.sendEmail.querySelector('.btn-spinner');
        const label = this.sendEmail.querySelector('.btn-label');
        spinner.style.display = 'inline-block';
        label.textContent = 'Sending...';

        try {
            const response = await fetch('/api/send-itinerary', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    email: email,
                    destination: this.currentDestination,
                    itinerary_content: this.currentItinerary
                })
            });

            const data = await response.json();

            if (response.ok) {
                // Show success message
                this.successText.textContent = data.message;
                this.emailSuccess.style.display = 'flex';

                // Close modal after 2 seconds
                setTimeout(() => {
                    this.closeEmailModalHandler();
                }, 2000);

                console.log('Itinerary sent successfully!');
            } else {
                // Show error
                this.emailError.textContent = data.detail || 'Failed to send email. Please try again.';
                this.emailError.style.display = 'block';
            }
        } catch (error) {
            console.error('Error sending email:', error);
            this.emailError.textContent = 'Network error. Please check your connection and try again.';
            this.emailError.style.display = 'block';
        } finally {
            // Re-enable button and hide loading
            this.sendEmail.disabled = false;
            spinner.style.display = 'none';
            label.textContent = 'Send ✓';
        }
    }
}

// Initialize the voice agent when page loads
document.addEventListener('DOMContentLoaded', () => {
    new VoiceAgent();
});
