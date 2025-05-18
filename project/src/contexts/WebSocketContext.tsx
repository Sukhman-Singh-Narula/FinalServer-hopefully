import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

// Define the shape of our context state and methods
interface WebSocketContextType {
  connected: boolean;
  connecting: boolean;
  connectionError: string | null;
  sendMessage: (data: Int16Array | ArrayBuffer | Blob) => void;
  reconnect: () => void;
}

// Default context value
const defaultContextValue: WebSocketContextType = {
  connected: false,
  connecting: false,
  connectionError: null,
  sendMessage: () => {},
  reconnect: () => {},
};

// Create the context
const WebSocketContext = createContext<WebSocketContextType>(defaultContextValue);

// Custom hook for using the WebSocket context
export const useWebSocket = () => useContext(WebSocketContext);

interface WebSocketProviderProps {
  children: ReactNode;
  // You can add server URL as a prop or use an environment variable
  serverUrl?: string;
}

export const WebSocketProvider: React.FC<WebSocketProviderProps> = ({ 
  children, 
  serverUrl = 'ws://localhost:8000/ws/{TEST_DEVICE_1000'
}) => {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Initialize WebSocket connection
  const initializeWebSocket = useCallback(() => {
    if (socket !== null) {
      socket.close();
    }

    setConnecting(true);
    setConnectionError(null);
    
    try {
      const newSocket = new WebSocket(serverUrl);
      
      newSocket.onopen = () => {
        console.log('WebSocket connection established');
        setConnected(true);
        setConnecting(false);
        setConnectionError(null);
      };
      
      newSocket.onclose = (event) => {
        console.log('WebSocket connection closed', event);
        setConnected(false);
        setConnecting(false);
        
        if (!event.wasClean) {
          setConnectionError(`Connection closed unexpectedly (code: ${event.code})`);
        }
      };
      
      newSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionError('Failed to connect to the server. Please try again.');
        setConnecting(false);
        setConnected(false);
      };
      
      setSocket(newSocket);
    } catch (error) {
      console.error('Error creating WebSocket:', error);
      setConnectionError('Failed to initialize WebSocket connection');
      setConnecting(false);
    }
  }, [serverUrl]);

  // Function to send messages through the WebSocket
  const sendMessage = useCallback((data: Int16Array | ArrayBuffer | Blob) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(data);
      } catch (error) {
        console.error('Error sending message:', error);
        setConnectionError('Failed to send audio data');
      }
    } else {
      console.warn('WebSocket is not connected');
    }
  }, [socket]);

  // Function to manually reconnect
  const reconnect = useCallback(() => {
    initializeWebSocket();
  }, [initializeWebSocket]);

  // Initialize WebSocket on component mount
  useEffect(() => {
    initializeWebSocket();
    
    // Clean up on unmount
    return () => {
      if (socket) {
        socket.close();
      }
    };
  }, [initializeWebSocket]);

  // The context value that will be provided
  const contextValue: WebSocketContextType = {
    connected,
    connecting,
    connectionError,
    sendMessage,
    reconnect,
  };

  return (
    <WebSocketContext.Provider value={contextValue}>
      {children}
    </WebSocketContext.Provider>
  );
};