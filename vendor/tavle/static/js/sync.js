/**
 * SyncManager Class
 * Handles all real-time synchronization via Socket.IO.
 * Connects the Whiteboard to the server and manages event flow.
 */
class SyncManager {
    constructor(whiteboard, tokenId, options = {}) {
        this.whiteboard = whiteboard;
        this.tokenId = tokenId;
        this.socket = null;
        this.connected = false;

        // User identity
        this.userId = options.userId || this._generateUserId();
        this.userName = options.userName || 'Anonymous';
        this.viewOnly = options.viewOnly === true || options.readonly === true;

        // Throttling for stroke points
        this.throttleInterval = options.throttleInterval || 16;  // ~60fps
        this.lastEmitTime = 0;
        this.pendingPoint = null;
        this.throttleTimer = null;

        // Cursor throttling (less frequent than strokes)
        this.cursorThrottleInterval = 50;  // ~20fps for cursors
        this.lastCursorEmitTime = 0;
        this.pendingCursor = null;
        this.cursorThrottleTimer = null;

        // Rejoin debounce (avoid spamming rejoin on multiple auth errors)
        this.lastRejoinTime = 0;
        this.rejoinDebounceMs = 2000;  // Minimum 2 seconds between rejoin attempts

        // Rate limit state
        this.rateLimited = false;
        this.rateLimitClearTimer = null;

        // Server URL
        this.serverUrl = options.serverUrl || window.location.origin;

        // Setup whiteboard user
        this.whiteboard.setLocalUser(this.userId, this.userName);

        // Bind whiteboard callbacks
        this._bindWhiteboardCallbacks();
    }

    // =========================================================================
    // Connection Management
    // =========================================================================

    /**
     * Set a callback to be notified of connection state changes
     * @param {Function} callback - Function to call with (connected: boolean)
     */
    onConnectionChange(callback) {
        this._connectionCallback = callback;
    }

    /**
     * Set a callback to be notified of rate limit state changes
     * @param {Function} callback - Function to call with (rateLimited: boolean)
     */
    onRateLimitChange(callback) {
        this._rateLimitCallback = callback;
    }

    /**
     * Set a callback for user-visible error messages (i18n key or plain string)
     * @param {Function} callback - Function to call with (messageKey: string)
     */
    onError(callback) {
        this._errorCallback = callback;
    }

    _notifyConnectionChange() {
        if (this._connectionCallback) {
            this._connectionCallback(this.connected);
        }
    }

    _notifyRateLimitChange() {
        if (this._rateLimitCallback) {
            this._rateLimitCallback(this.rateLimited);
        }
    }

    _notifyError(messageKey) {
        if (this._errorCallback) {
            this._errorCallback(messageKey);
        }
    }

    _handleImageAddFailure(error) {
        if (error.imageId) {
            this.whiteboard.removeImageLocal(error.imageId);
        }

        const message = error.message || '';
        if (message.includes('Board image limit')) {
            this._notifyError('errors.imageBoardFull');
        } else if (message.includes('Invalid image data')) {
            this._notifyError('errors.imageTooLarge');
        } else {
            this._notifyError('errors.imageUploadFailed');
        }
    }

    _setRateLimited(limited) {
        this.rateLimited = limited;
        this._notifyRateLimitChange();
        
        // Auto-clear rate limit status after 60 seconds
        if (limited) {
            if (this.rateLimitClearTimer) {
                clearTimeout(this.rateLimitClearTimer);
            }
            this.rateLimitClearTimer = setTimeout(() => {
                this.rateLimited = false;
                this._notifyRateLimitChange();
            }, 60000);
        }
    }

    connect() {
        return new Promise((resolve, reject) => {
            try {
                this.socket = io(this.serverUrl, {
                    transports: ['websocket', 'polling'],
                    reconnection: true,
                    reconnectionAttempts: Infinity,
                    reconnectionDelay: 1000,
                    reconnectionDelayMax: 5000
                });

                // Track if this is the initial connection
                let initialConnect = true;

                this.socket.on('connect', () => {
                    console.log('Socket connected');
                    this.connected = true;
                    this._notifyConnectionChange();
                    this.joinRoom();
                    
                    if (initialConnect) {
                        initialConnect = false;
                        resolve();
                    } else {
                        console.log('Socket reconnected - rejoined room automatically');
                    }
                });

                this.socket.on('disconnect', (reason) => {
                    console.log('Socket disconnected:', reason);
                    this.connected = false;
                    this._notifyConnectionChange();
                });

                this.socket.on('connect_error', (error) => {
                    console.error('Socket connection error:', error);
                    this.connected = false;
                    this._notifyConnectionChange();
                    if (initialConnect) {
                        reject(error);
                    }
                });

                // Handle authentication and rate limit errors
                this.socket.on('error', (error) => {
                    console.warn('Socket error:', error);
                    
                    // Handle rate limiting
                    if (error.code === 'RATE_LIMITED' || 
                        (error.message && error.message.includes('Rate limit'))) {
                        console.warn('Rate limited by server');
                        this._setRateLimited(true);
                        return;
                    }
                    
                    // Handle authentication errors - rejoin room (with debounce)
                    if (error.code === 'AUTH_REQUIRED' || 
                        (error.message && error.message.includes('Not authenticated'))) {
                        const now = Date.now();
                        if (now - this.lastRejoinTime >= this.rejoinDebounceMs) {
                            console.log('Session expired - rejoining room...');
                            this.lastRejoinTime = now;
                            this.joinRoom();
                        }
                        return;
                    }

                    if (error.code === 'IMAGE_ADD_FAILED') {
                        this._handleImageAddFailure(error);
                    }
                });

                // Bind inbound event handlers
                this._bindSocketEvents();

            } catch (error) {
                reject(error);
            }
        });
    }

    disconnect() {
        if (this.socket) {
            this.socket.emit('leave', { 
                tokenId: this.tokenId,
                userId: this.userId
            });
            this.socket.disconnect();
            this.socket = null;
            this.connected = false;
        }
    }

    joinRoom() {
        if (this.socket && this.connected) {
            this.socket.emit('join', { 
                tokenId: this.tokenId,
                userId: this.userId,
                userName: this.userName
            });
        }
    }

    setUserName(name) {
        this.userName = name;
        this.whiteboard.setLocalUser(this.userId, name);
    }

    // =========================================================================
    // Whiteboard Callbacks
    // =========================================================================

    _bindWhiteboardCallbacks() {
        if (this.viewOnly) {
            return;
        }
        // Stroke point (throttled)
        this.whiteboard.onStrokePoint = (data) => {
            this._emitThrottled('stroke-point', {
                tokenId: this.tokenId,
                ...data
            });
        };

        // Stroke complete
        this.whiteboard.onStrokeComplete = (data) => {
            // Flush any pending throttled point first
            this._flushThrottled();

            this._emit('stroke-complete', {
                tokenId: this.tokenId,
                ...data
            });
        };

        // Stroke update (move/transform)
        this.whiteboard.onStrokeUpdate = (data) => {
            this._emit('stroke-update', {
                tokenId: this.tokenId,
                ...data
            });
        };

        // Stroke delete
        this.whiteboard.onStrokeDelete = (data) => {
            this._emit('stroke-delete', {
                tokenId: this.tokenId,
                ...data
            });
        };

        // Clear canvas
        this.whiteboard.onClear = () => {
            this._emit('clear', {
                tokenId: this.tokenId
            });
        };

        // Image add
        this.whiteboard.onImageAdd = (data) => {
            if (!this.connected) {
                this.whiteboard.removeImageLocal(data.id);
                this._notifyError('errors.imageUploadFailed');
                return;
            }
            this._emit('image-add', {
                tokenId: this.tokenId,
                imageId: data.id,
                data: data.data,
                x: data.x,
                y: data.y,
                width: data.width,
                height: data.height,
                transform: data.transform,
                zIndex: data.zIndex
            });
        };

        this.whiteboard.onImageError = (messageKey) => {
            this._notifyError(`errors.${messageKey}`);
        };

        // Image update (move/transform)
        this.whiteboard.onImageUpdate = (data) => {
            this._emit('image-update', {
                tokenId: this.tokenId,
                ...data
            });
        };

        // Image delete
        this.whiteboard.onImageDelete = (data) => {
            this._emit('image-delete', {
                tokenId: this.tokenId,
                ...data
            });
        };

        // Cursor move (throttled)
        this.whiteboard.onCursorMove = (cursor) => {
            this._emitCursorThrottled({
                tokenId: this.tokenId,
                userId: this.userId,
                userName: this.userName,
                cursor: cursor
            });
        };
    }
    // =========================================================================
    // Socket Event Handlers (Inbound)
    // =========================================================================

    _bindSocketEvents() {
        // Joined room confirmation
        this.socket.on('joined', (data) => {
            console.log('Joined room:', data.tokenId);
        });

        // Remote stroke point
        this.socket.on('remote-stroke-point', (data) => {
            this.whiteboard.applyRemoteStrokePoint(data);
        });

        // Remote stroke complete
        this.socket.on('remote-stroke-complete', (data) => {
            this.whiteboard.applyRemoteStrokeComplete(data);
        });

        // Remote stroke update
        this.socket.on('remote-stroke-update', (data) => {
            this.whiteboard.applyRemoteStrokeUpdate(data);
        });

        // Remote stroke delete
        this.socket.on('remote-stroke-delete', (data) => {
            this.whiteboard.applyRemoteStrokeDelete(data);
        });

        // Remote clear
        this.socket.on('remote-clear', (data) => {
            this.whiteboard.applyRemoteClear();
        });

        // Remote image add
        this.socket.on('remote-image-add', (data) => {
            this.whiteboard.applyRemoteImageAdd(data);
        });

        // Remote image update
        this.socket.on('remote-image-update', (data) => {
            this.whiteboard.applyRemoteImageUpdate(data);
        });

        // Remote image delete
        this.socket.on('remote-image-delete', (data) => {
            this.whiteboard.applyRemoteImageDelete(data);
        });

        // Remote cursor update
        this.socket.on('remote-cursor', (data) => {
            this.whiteboard.updateRemoteUser(data.userId, {
                name: data.userName,
                cursor: data.cursor
            });
        });

        // User joined
        this.socket.on('user-joined', (data) => {
            console.log('User joined:', data.userName);
            this.whiteboard.updateRemoteUser(data.userId, {
                name: data.userName
            });
        });

        // User left
        this.socket.on('user-left', (data) => {
            console.log('User left:', data.userId);
            this.whiteboard.removeRemoteUser(data.userId);
        });
    }

    // =========================================================================
    // Emission Helpers
    // =========================================================================

    _emit(event, data) {
        if (this.socket && this.connected) {
            this.socket.emit(event, data);
        }
    }

    _emitThrottled(event, data) {
        const now = Date.now();

        if (now - this.lastEmitTime >= this.throttleInterval) {
            // Enough time has passed, emit immediately
            this._emit(event, data);
            this.lastEmitTime = now;
            this.pendingPoint = null;
        } else {
            // Store for later emission
            this.pendingPoint = { event, data };

            // Set up timer if not already set
            if (!this.throttleTimer) {
                const delay = this.throttleInterval - (now - this.lastEmitTime);
                this.throttleTimer = setTimeout(() => {
                    this._flushThrottled();
                }, delay);
            }
        }
    }

    _flushThrottled() {
        if (this.throttleTimer) {
            clearTimeout(this.throttleTimer);
            this.throttleTimer = null;
        }

        if (this.pendingPoint) {
            this._emit(this.pendingPoint.event, this.pendingPoint.data);
            this.pendingPoint = null;
            this.lastEmitTime = Date.now();
        }
    }

    _emitCursorThrottled(data) {
        const now = Date.now();

        if (now - this.lastCursorEmitTime >= this.cursorThrottleInterval) {
            this._emit('cursor-move', data);
            this.lastCursorEmitTime = now;
            this.pendingCursor = null;
        } else {
            this.pendingCursor = data;

            if (!this.cursorThrottleTimer) {
                const delay = this.cursorThrottleInterval - (now - this.lastCursorEmitTime);
                this.cursorThrottleTimer = setTimeout(() => {
                    this._flushCursorThrottled();
                }, delay);
            }
        }
    }

    _flushCursorThrottled() {
        if (this.cursorThrottleTimer) {
            clearTimeout(this.cursorThrottleTimer);
            this.cursorThrottleTimer = null;
        }

        if (this.pendingCursor) {
            this._emit('cursor-move', this.pendingCursor);
            this.pendingCursor = null;
            this.lastCursorEmitTime = Date.now();
        }
    }

    _generateUserId() {
        // Try to get from localStorage for persistence across sessions
        let oduserId = localStorage.getItem('whiteboardUserId');
        if (!oduserId) {
            oduserId = 'user-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem('whiteboardUserId', oduserId);
        }
        return oduserId;
    }

    // =========================================================================
    // Document Persistence
    // =========================================================================

    async loadDocument() {
        try {
            const response = await fetch(`/get/${this.tokenId}`);

            if (!response.ok) {
                throw new Error(`Failed to load document: ${response.status}`);
            }

            const data = await response.json();

            // Import strokes to whiteboard
            if (data.strokes && Array.isArray(data.strokes)) {
                const strokes = data.strokes.map(s => ({
                    id: s.id,
                    points: s.points,
                    color: s.color,
                    strokeWidth: s.strokeWidth,
                    transform: s.transform || { x: 0, y: 0, scale: 1 },
                    zIndex: s.zIndex
                }));
                this.whiteboard.importStrokes(strokes);
            }

            // Import images to whiteboard
            if (data.images && Array.isArray(data.images)) {
                const images = data.images.map(img => ({
                    id: img.id,
                    data: img.data,
                    x: img.x,
                    y: img.y,
                    width: img.width,
                    height: img.height,
                    transform: img.transform || { x: 0, y: 0, scale: 1 },
                    zIndex: img.zIndex
                }));
                this.whiteboard.importImages(images);
            }

            return data;
        } catch (error) {
            console.error('Error loading document:', error);
            throw error;
        }
    }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SyncManager;
}
