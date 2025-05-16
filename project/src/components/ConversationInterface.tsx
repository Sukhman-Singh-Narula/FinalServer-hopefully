import React, { useState, useEffect, useRef } from 'react';
import { Mic, MicOff, Volume2, Loader, WifiOff } from 'lucide-react';
import { useAudioRecorder } from '../hooks/useAudioRecorder';
import { useWebSocketConnection } from '../hooks/useWebSocketConnection';
import { useAudioPlayer } from '../hooks/useAudioPlayer';
import AudioVisualizer from './AudioVisualizer';

type ConversationState = 'idle' | 'connecting' | 'listening' | 'processing' | 'responding' | 'error';

const ConversationInterface: React.FC = () => {
  const [conversationState, setConversationState] = useState<ConversationState>('idle');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [debugMessages, setDebugMessages] = useState<string[]>([]);
  const [connectionAttempts, setConnectionAttempts] = useState(0);
  
  const { 
    isRecording, 
    startRecording, 
    stopRecording, 
    audioData,
    audioAnalyser,
    hasPermission,
    permissionError,
    requestPermission
  } = useAudioRecorder();
  
  const { 
    connected, 
    connect, 
    disconnect, 
    sendAudioChunk, 
    responseAudio
  } = useWebSocketConnection();
  
  const { playAudio } = useAudioPlayer();
  const audioChunksRef = useRef<Uint8Array[]>([]);
  const connectionTimeoutRef = useRef<number | null>(null);

  // Add a debug function
  const addDebugMessage = (message: string) => {
    console.log(message);
    setDebugMessages(prev => [...prev.slice(-9), message]);
  };

  // Effect to handle WebSocket connection state changes
  useEffect(() => {
    if (connected) {
      addDebugMessage('WebSocket connected successfully');
      
      // If we were in connecting state, move to the next step
      if (conversationState === 'connecting') {
        addDebugMessage('Connection successful, starting recording');
        startRecording();
      }
    } else {
      // Only log disconnection if we were previously connected or trying to connect
      if (conversationState === 'connecting' || conversationState === 'listening' || 
          conversationState === 'processing' || conversationState === 'responding') {
        addDebugMessage('WebSocket disconnected');
        
        // If we were in the middle of a conversation, handle the disconnection
        if (conversationState === 'listening' || conversationState === 'processing') {
          setErrorMessage('Connection to server lost. Please try again.');
          setConversationState('error');
        }
      }
    }
  }, [connected, conversationState, startRecording]);

  // Effect to handle recording state changes
  useEffect(() => {
    if (isRecording && conversationState !== 'listening') {
      setConversationState('listening');
      addDebugMessage('Started listening');
    } else if (!isRecording && conversationState === 'listening') {
      setConversationState('processing');
      addDebugMessage('Stopped listening, processing...');
    }
  }, [isRecording, conversationState]);

  // Effect to handle audio data during recording
  useEffect(() => {
    if (audioData && conversationState === 'listening' && connected) {
      audioChunksRef.current.push(audioData);
      sendAudioChunk(audioData);
      
      // Log occasionally to avoid flooding the console
      if (audioChunksRef.current.length % 10 === 0) {
        addDebugMessage(`Sent ${audioChunksRef.current.length} audio chunks`);
      }
    }
  }, [audioData, conversationState, connected, sendAudioChunk]);

  // Effect to handle response from server
  useEffect(() => {
    if (responseAudio && (conversationState === 'processing' || conversationState === 'listening')) {
      addDebugMessage(`Received response (${responseAudio.length} bytes)`);
      
      // Stop recording if still listening
      if (conversationState === 'listening') {
        stopRecording();
      }
      
      setConversationState('responding');
      
      playAudio(responseAudio, () => {
        addDebugMessage('Finished playing response');
        setConversationState('idle');
      });
    }
  }, [responseAudio, conversationState, stopRecording, playAudio]);

  // Effect to handle microphone permission errors
  useEffect(() => {
    if (permissionError) {
      setErrorMessage(permissionError);
      setConversationState('error');
      addDebugMessage(`Permission error: ${permissionError}`);
    }
  }, [permissionError]);

  // Handle connection timeout
  useEffect(() => {
    if (conversationState === 'connecting') {
      // Set a timeout for connection
      connectionTimeoutRef.current = window.setTimeout(() => {
        if (!connected) {
          addDebugMessage('Connection attempt timed out');
          setErrorMessage('Could not connect to the server. Please try again.');
          setConversationState('error');
        }
      }, 5000); // 5 second timeout
    }
    
    return () => {
      // Clear timeout when component unmounts or state changes
      if (connectionTimeoutRef.current) {
        window.clearTimeout(connectionTimeoutRef.current);
        connectionTimeoutRef.current = null;
      }
    };
  }, [conversationState, connected]);

  // Start conversation handler
  const handleStartConversation = async () => {
    if (conversationState !== 'idle' && conversationState !== 'error') return;
    
    audioChunksRef.current = [];
    setErrorMessage('');
    setConversationState('connecting');
    addDebugMessage('Starting conversation...');
    
    try {
      // First, request microphone permission if needed
      if (!hasPermission) {
        addDebugMessage('Requesting microphone permission');
        const granted = await requestPermission();
        if (!granted) {
          return; // Error message is handled by the hook
        }
        addDebugMessage('Microphone permission granted');
      }
      
      // Then try to connect to WebSocket server
      addDebugMessage('Connecting to WebSocket server');
      setConnectionAttempts(prev => prev + 1);
      
      // Try to connect - the connected state will be handled in the useEffect above
      await connect();
      
    } catch (error) {
      const message = error instanceof Error ? error.message : 'An unknown error occurred';
      setErrorMessage(message);
      setConversationState('error');
      addDebugMessage(`Error: ${message}`);
    }
  };

  // Stop conversation handler
  const handleStopConversation = () => {
    if (conversationState !== 'listening') return;
    addDebugMessage('Stopping conversation');
    stopRecording();
  };

  // Retry handler
  const handleRetry = () => {
    setConversationState('idle');
    setErrorMessage('');
    addDebugMessage('Retrying after error');
    
    // Disconnect first to ensure clean slate
    disconnect();
  };

  return (
    <div className="bg-white rounded-2xl shadow-lg p-6 transition-all duration-300">
      <div className="flex flex-col items-center">
        <div className="w-full h-32 mb-6 flex items-center justify-center">
          {conversationState === 'listening' && audioAnalyser ? (
            <AudioVisualizer audioAnalyser={audioAnalyser} />
          ) : (
            <div className={`w-48 h-48 rounded-full flex items-center justify-center transition-all duration-300 ${getStateBackground(conversationState)}`}>
              {getStateIcon(conversationState)}
            </div>
          )}
        </div>

        <div className="min-h-12 mb-6 text-center">
          {conversationState === 'error' ? (
            <p className="text-red-500">{errorMessage}</p>
          ) : (
            <p className="text-gray-700">{getStateMessage(conversationState)}</p>
          )}
          
          {/* Connection status */}
          <p className={`text-sm mt-2 ${connected ? 'text-green-600' : 'text-gray-500'}`}>
            {connected ? 'Connected to server' : 
              (conversationState === 'connecting' ? 'Connecting...' : 'Not connected')}
          </p>
        </div>

        <button
          onClick={
            conversationState === 'idle' || conversationState === 'error'
              ? handleStartConversation 
              : conversationState === 'listening' 
                ? handleStopConversation 
                : undefined
          }
          disabled={conversationState === 'connecting' || conversationState === 'processing' || conversationState === 'responding'}
          className={`px-8 py-4 rounded-full font-medium text-white transition-all duration-300 transform hover:scale-105 active:scale-95 ${
            conversationState === 'idle' || conversationState === 'error'
              ? 'bg-blue-500 hover:bg-blue-600'
              : conversationState === 'listening'
                ? 'bg-red-500 hover:bg-red-600'
                : 'bg-gray-400 cursor-not-allowed'
          }`}
        >
          {conversationState === 'idle'
            ? 'Start Conversation'
            : conversationState === 'connecting'
              ? 'Connecting...'
              : conversationState === 'listening'
                ? 'Stop Listening'
                : conversationState === 'error'
                  ? 'Try Again'
                  : conversationState === 'processing'
                    ? 'Processing...'
                    : 'Responding...'}
        </button>
        
        {/* Debug information */}
        <div className="mt-6 w-full text-xs font-mono bg-gray-100 p-2 rounded max-h-40 overflow-y-auto">
          <h3 className="font-bold mb-1">Connection Status:</h3>
          <p className={connected ? "text-green-600" : "text-red-600"}>
            WebSocket: {connected ? "Connected" : "Disconnected"}
          </p>
          <p className={hasPermission ? "text-green-600" : "text-red-600"}>
            Microphone: {hasPermission ? "Granted" : "Not granted"}
          </p>
          <p className="text-gray-600">
            Connection attempts: {connectionAttempts}
          </p>
          
          <h3 className="font-bold mt-2 mb-1">Debug Log:</h3>
          <div className="space-y-1">
            {debugMessages.map((msg, idx) => (
              <div key={idx} className="text-gray-700">{msg}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const getStateMessage = (state: ConversationState): string => {
  switch (state) {
    case 'idle':
      return 'Click the button to start a conversation';
    case 'connecting':
      return 'Connecting to server...';
    case 'listening':
      return 'Listening to your voice...';
    case 'processing':
      return 'Processing your request...';
    case 'responding':
      return 'Playing response...';
    default:
      return '';
  }
};

const getStateBackground = (state: ConversationState): string => {
  switch (state) {
    case 'idle':
      return 'bg-gray-100';
    case 'connecting':
      return 'bg-yellow-100';
    case 'listening':
      return 'bg-blue-100';
    case 'processing':
      return 'bg-purple-100';
    case 'responding':
      return 'bg-green-100';
    case 'error':
      return 'bg-red-100';
    default:
      return 'bg-gray-100';
  }
};

const getStateIcon = (state: ConversationState) => {
  switch (state) {
    case 'idle':
      return <Mic className="h-12 w-12 text-blue-500" />;
    case 'connecting':
      return <Loader className="h-12 w-12 text-yellow-500 animate-spin" />;
    case 'listening':
      return <Mic className="h-12 w-12 text-blue-600 animate-pulse" />;
    case 'processing':
      return <Loader className="h-12 w-12 text-purple-600 animate-spin" />;
    case 'responding':
      return <Volume2 className="h-12 w-12 text-green-600" />;
    case 'error':
      return <WifiOff className="h-12 w-12 text-red-500" />;
    default:
      return <Mic className="h-12 w-12 text-blue-500" />;
  }
};

export default ConversationInterface;