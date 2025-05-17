import { useState, useEffect, useRef, useCallback } from 'react';

// Use the exact same URL format that works in your logs
const WEBSOCKET_URL = 'ws://127.0.0.1:8000/ws/TEST_DEVICE_1234';

interface WebSocketHook {
  connected: boolean;
  connect: () => Promise<void>;
  disconnect: () => void;
  sendAudioChunk: (chunk: Uint8Array) => void;
  responseAudio: Uint8Array | null;
}

export const useWebSocketConnection = (): WebSocketHook => {
  const [connected, setConnected] = useState<boolean>(false);
  const [responseAudio, setResponseAudio] = useState<Uint8Array | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  
  // Connect to the WebSocket server
  const connect = useCallback(async (): Promise<void> => {
    return new Promise((resolve, reject) => {
      try {
        // Don't create a new connection if one already exists
        if (websocketRef.current && (websocketRef.current.readyState === WebSocket.CONNECTING || 
                                     websocketRef.current.readyState === WebSocket.OPEN)) {
          console.log('WebSocket already connected or connecting');
          setConnected(websocketRef.current.readyState === WebSocket.OPEN);
          resolve();
          return;
        }
        
        console.log('Connecting to WebSocket server at:', WEBSOCKET_URL);
        
        // Create a new WebSocket connection
        const ws = new WebSocket(WEBSOCKET_URL);
        
        // Set up event handlers
        ws.onopen = () => {
          console.log('WebSocket connection established successfully');
          setConnected(true);
          resolve();
        };
        
        ws.onclose = (event) => {
          console.log('WebSocket connection closed:', event.code, event.reason);
          setConnected(false);
        };
        
        ws.onerror = (event) => {
          console.error('WebSocket error:', event);
          // Don't reject if we're already connected - this happens sometimes on reconnection attempts
          if (!connected) {
            reject(new Error('WebSocket connection failed'));
          }
        };
        
        ws.onmessage = (event) => {
          console.log('Received message from server:', typeof event.data);
          
          // Handle different message types
          if (typeof event.data === 'string') {
            // Try to parse as JSON first
            try {
              const response = JSON.parse(event.data);
              console.log('Parsed JSON response:', response);
              
              // If we received an acknowledgment, we don't need to do anything special
              if (response.type === 'ack') {
                console.log('Received acknowledgment from server');
              } else if (response.type === 'info') {
                console.log('Received info from server:', response.message);
              }
              
              // If it's a plain text without JSON formatting, use it as audio response
              if (typeof response === 'string' || (response.message && typeof response.message === 'string')) {
                const textToEncode = typeof response === 'string' ? response : response.message;
                const encoder = new TextEncoder();
                const uint8Array = encoder.encode(textToEncode);
                setResponseAudio(uint8Array);
              }
            } catch (error) {
              // If it's not JSON, treat it as plain text for TTS
              console.log('Received plain text response:', event.data);
              
              const encoder = new TextEncoder();
              const uint8Array = encoder.encode(event.data);
              setResponseAudio(uint8Array);
            }
          } else if (event.data instanceof Blob) {
            // Handle binary audio data sent back from the server
            console.log('Received binary data of size:', event.data.size);
            
            // Convert Blob to Uint8Array
            event.data.arrayBuffer().then((buffer) => {
              const uint8Array = new Uint8Array(buffer);
              setResponseAudio(uint8Array);
            });
          }
        };
        
        // Store the WebSocket instance
        websocketRef.current = ws;
        
      } catch (error) {
        console.error('Failed to create WebSocket:', error);
        reject(error);
      }
    });
  }, [connected]);
  
  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    console.log('Disconnecting WebSocket...');
    if (websocketRef.current) {
      // Only close if it's connected
      if (websocketRef.current.readyState === WebSocket.OPEN ||
          websocketRef.current.readyState === WebSocket.CONNECTING) {
        websocketRef.current.close();
      }
      websocketRef.current = null;
    }
    
    setConnected(false);
  }, []);
  
  // Send audio chunk to WebSocket
  const sendAudioChunk = useCallback((chunk: Uint8Array) => {
    if (!websocketRef.current) {
      console.warn('Cannot send audio chunk: No WebSocket connection');
      return;
    }
    
    if (websocketRef.current.readyState !== WebSocket.OPEN) {
      console.warn('Cannot send audio chunk: WebSocket not open, state:', 
        websocketRef.current.readyState === WebSocket.CONNECTING ? 'CONNECTING' : 
        websocketRef.current.readyState === WebSocket.CLOSING ? 'CLOSING' : 'CLOSED');
      return;
    }
    
    console.log('Sending audio chunk, size:', chunk.length);
    
    try {
      // Send the audio chunk as binary data
      websocketRef.current.send(chunk);
    } catch (error) {
      console.error('Error sending audio chunk:', error);
    }
  }, []);
  
  // Set up a ping/keep-alive mechanism
  useEffect(() => {
    let pingInterval: number | null = null;
    
    if (connected && websocketRef.current) {
      // Send a small ping every 15 seconds to keep the connection alive
      pingInterval = window.setInterval(() => {
        if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
          try {
            // Send a small text message as a ping
            websocketRef.current.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }));
            console.log('Sent ping to keep connection alive');
          } catch (error) {
            console.error('Error sending ping:', error);
          }
        }
      }, 15000);
    }
    
    return () => {
      if (pingInterval !== null) {
        window.clearInterval(pingInterval);
      }
    };
  }, [connected]);
  
  // Clean up on unmount
  useEffect(() => {
    console.log('WebSocket hook initialized');
    
    return () => {
      console.log('WebSocket hook cleanup');
      disconnect();
    };
  }, [disconnect]);
  
  return {
    connected,
    connect,
    disconnect,
    sendAudioChunk,
    responseAudio,
  };
};