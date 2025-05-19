import React, { useState, useEffect, useRef } from 'react';
import { Mic, StopCircle, RotateCcw } from 'lucide-react';
import AudioWaveform from './AudioWaveform';
import StatusIndicator from './StatusIndicator';

// Feature detection for AudioWorklet
const supportsAudioWorklet =
  typeof window !== 'undefined' &&
  window.AudioContext &&
  'audioWorklet' in AudioContext.prototype;

const AudioRecorder: React.FC = () => {
  // States
  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState<Uint8Array | null>(null);
  const [deviceId] = useState(`TEST_DEVICE_${Math.floor(Math.random() * 9000) + 1000}`);
  const [messageCount, setMessageCount] = useState(0);
  const [isWorkletLoaded, setIsWorkletLoaded] = useState(false);
  const [isWorkletUsed, setIsWorkletUsed] = useState(false);

  // Debug state
  const [debugMode, setDebugMode] = useState(true); // Start with debug visible
  const [debugLog, setDebugLog] = useState<string[]>([]);

  // Refs
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const webSocketRef = useRef<WebSocket | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const audioSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const messageCounterRef = useRef(0);
  const isRecordingRef = useRef(false); // For callbacks to access current state

  // Add debug log function
  const addDebugLog = (message: string) => {
    console.log(message);
    setDebugLog(prev => [...prev.slice(-19), message]);
  };

  // Update isRecordingRef when isRecording changes
  useEffect(() => {
    isRecordingRef.current = isRecording;
  }, [isRecording]);

  // Initialize AudioWorklet if supported
  useEffect(() => {
    const initAudioWorklet = async () => {
      if (!supportsAudioWorklet) {
        addDebugLog('⚠️ AudioWorklet not supported in this browser, will use fallback');
        return;
      }

      try {
        if (!audioContextRef.current) {
          audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
        }

        // Check if worklet is already loaded
        if (isWorkletLoaded) return;

        // Load audio worklet
        await audioContextRef.current.audioWorklet.addModule('/audioWorkletProcessor.js');
        setIsWorkletLoaded(true);
        addDebugLog('✅ AudioWorklet loaded successfully');
      } catch (error) {
        addDebugLog(`❌ Failed to load AudioWorklet: ${error}`);
        setIsWorkletLoaded(false);
      }
    };

    initAudioWorklet();
  }, [isWorkletLoaded]);

  // Connect to WebSocket server
  useEffect(() => {
    const connectWebSocket = () => {
      setIsConnecting(true);
      setErrorMessage(null);

      // Use your server URL here - Make sure this matches your server!
      const wsUrl = `ws://localhost:8000/ws/${deviceId}`;
      addDebugLog(`🔄 Connecting to WebSocket at ${wsUrl}`);

      try {
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          addDebugLog('🟢 WebSocket connected successfully');
          setIsConnected(true);
          setIsConnecting(false);
        };

        ws.onmessage = (event) => {
          try {
            if (typeof event.data === 'string') {
              addDebugLog(`📥 Received: ${event.data.substring(0, 50)}${event.data.length > 50 ? '...' : ''}`);
            } else {
              addDebugLog(`📥 Received binary data: ${event.data.size || 'unknown'} bytes`);
            }
          } catch (e) {
            addDebugLog(`❌ Error processing message: ${e}`);
          }
        };

        ws.onclose = (event) => {
          addDebugLog(`🔴 WebSocket closed: code=${event.code}, reason=${event.reason || 'none'}`);
          setIsConnected(false);
          setIsConnecting(false);

          // Stop recording if active
          if (isRecording) {
            stopRecording();
          }
        };

        ws.onerror = (error) => {
          addDebugLog(`❌ WebSocket error: ${error}`);
          setErrorMessage('Connection error. Please try again.');
          setIsConnected(false);
          setIsConnecting(false);
        };

        webSocketRef.current = ws;
      } catch (error) {
        addDebugLog(`❌ Error creating WebSocket: ${error}`);
        setErrorMessage('Failed to create WebSocket connection');
        setIsConnected(false);
        setIsConnecting(false);
      }
    };

    connectWebSocket();

    // Cleanup on unmount
    return () => {
      if (webSocketRef.current) {
        webSocketRef.current.close();
      }
    };
  }, [deviceId]);

  // Setup audio visualization (for waveform)
  useEffect(() => {
    const setupAudioVisualization = async () => {
      try {
        if (!audioContextRef.current) {
          audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
          addDebugLog('🎵 Created new AudioContext');
        }

        // Create analyzer for visualization
        if (!analyserRef.current && audioContextRef.current) {
          const analyser = audioContextRef.current.createAnalyser();
          analyser.fftSize = 256;
          analyserRef.current = analyser;
          addDebugLog('📊 Created audio analyzer');
        }

        // Update audio level for visualization
        const updateAudioLevel = () => {
          if (analyserRef.current) {
            const bufferLength = analyserRef.current.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);
            analyserRef.current.getByteTimeDomainData(dataArray);
            setAudioLevel(dataArray);

            animationFrameRef.current = requestAnimationFrame(updateAudioLevel);
          }
        };

        updateAudioLevel();
      } catch (error) {
        addDebugLog(`❌ Error setting up audio visualization: ${error}`);
      }
    };

    setupAudioVisualization();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, []);

  // SIMPLIFIED APPROACH: Direct ScriptProcessor use for reliable performance
  const startRecording = async () => {
    try {
      if (!isConnected) {
        setErrorMessage('Not connected to server. Please try again.');
        return;
      }

      // Reset counter
      messageCounterRef.current = 0;
      setMessageCount(0);

      // Request access to the microphone
      addDebugLog('🎤 Requesting microphone access...');
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true
        }
      });

      mediaStreamRef.current = stream;
      addDebugLog('✅ Microphone access granted');

      // Make sure audio context is initialized
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      } else if (audioContextRef.current.state === 'suspended') {
        await audioContextRef.current.resume();
      }

      const audioContext = audioContextRef.current;

      // Create media stream source
      const source = audioContext.createMediaStreamSource(stream);
      audioSourceRef.current = source;

      // Connect to analyzer for visualization
      if (analyserRef.current) {
        source.connect(analyserRef.current);
      }

      // Create ScriptProcessorNode for audio processing
      // Using a smaller buffer size for less latency
      const processor = audioContext.createScriptProcessor(1024, 1, 1);
      processorRef.current = processor;

      // Function to send audio data
      const sendAudioData = (audioData: ArrayBuffer) => {
        if (!webSocketRef.current || webSocketRef.current.readyState !== WebSocket.OPEN) return;

        try {
          webSocketRef.current.send(audioData);
          messageCounterRef.current++;

          if (messageCounterRef.current % 10 === 0) {
            setMessageCount(messageCounterRef.current);
            addDebugLog(`📤 Sent ${messageCounterRef.current} audio chunks`);
          }
        } catch (e) {
          addDebugLog(`❌ Error sending audio: ${e}`);
        }
      };

      // Process audio data
      processor.onaudioprocess = (event) => {
        if (!isRecordingRef.current) return;

        // Get audio data from input channel
        const inputData = event.inputBuffer.getChannelData(0);

        // Convert to Int16Array (16-bit PCM)
        const pcmData = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          // Convert float [-1.0,1.0] to int [-32768,32767]
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // Send to server - IMPORTANT: convert to ArrayBuffer
        sendAudioData(pcmData.buffer);
      };

      // Connect processor - CRITICAL for audio flow
      source.connect(processor);
      processor.connect(audioContext.destination);

      setIsRecording(true);
      addDebugLog('🎙️ Recording started! Audio is streaming to server...');

    } catch (error) {
      console.error('Error starting recording:', error);
      addDebugLog(`❌ Recording error: ${error}`);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Failed to start recording. Please check microphone permissions.'
      );
    }
  };

  // Stop recording
  const stopRecording = () => {
    setIsRecording(false);

    // Stop and disconnect audio nodes
    if (processorRef.current && audioContextRef.current) {
      try {
        processorRef.current.disconnect();
        processorRef.current = null;
      } catch (e) {
        addDebugLog(`Error disconnecting processor: ${e}`);
      }
    }

    if (audioSourceRef.current) {
      try {
        audioSourceRef.current.disconnect();
        audioSourceRef.current = null;
      } catch (e) {
        addDebugLog(`Error disconnecting source: ${e}`);
      }
    }

    // Stop all tracks from the stream
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
      addDebugLog('🛑 Stopped media stream');
    }

    // Send end-of-stream signal to server
    if (webSocketRef.current && webSocketRef.current.readyState === WebSocket.OPEN) {
      try {
        const endMessage = JSON.stringify({ type: 'end_stream' });
        webSocketRef.current.send(endMessage);
        addDebugLog(`📤 Sent end_stream message: ${endMessage}`);
      } catch (e) {
        addDebugLog(`❌ Error sending end_stream: ${e}`);
      }
    }

    addDebugLog(`🛑 Recording stopped after sending ${messageCounterRef.current} chunks`);
  };

  // Reconnect to WebSocket server
  const reconnect = () => {
    if (webSocketRef.current) {
      webSocketRef.current.close();
    }

    setIsConnecting(true);
    addDebugLog('🔄 Reconnecting to WebSocket...');

    // Short delay before reconnecting
    setTimeout(() => {
      // Create new WebSocket connection
      const wsUrl = `ws://localhost:8000/ws/${deviceId}`;
      addDebugLog(`🔄 Reconnecting to ${wsUrl}`);

      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        addDebugLog('🟢 WebSocket reconnected successfully');
        setIsConnected(true);
        setIsConnecting(false);
        setErrorMessage(null);
      };

      ws.onclose = () => {
        addDebugLog('🔴 WebSocket disconnected');
        setIsConnected(false);
        setIsConnecting(false);
      };

      ws.onerror = (error) => {
        addDebugLog(`❌ WebSocket error on reconnect: ${error}`);
        setErrorMessage('Connection error. Please try again.');
        setIsConnected(false);
        setIsConnecting(false);
      };

      webSocketRef.current = ws;
    }, 500);
  };

  return (
    <div className="w-full max-w-md mx-auto bg-white rounded-xl shadow-md overflow-hidden p-6">
      <h2 className="text-2xl font-semibold text-gray-800 text-center mb-6">
        Voice Recording <span className="text-xs text-gray-500">Device: {deviceId}</span>
      </h2>

      {/* Audio visualization */}
      <AudioWaveform audioData={audioLevel} isRecording={isRecording} />

      {/* Connection status */}
      <StatusIndicator
        isConnected={isConnected}
        isConnecting={isConnecting}
        error={errorMessage}
      />

      {/* Recording controls */}
      <div className="mt-6 flex flex-col items-center">
        <button
          onClick={isRecording ? stopRecording : startRecording}
          disabled={!isConnected || isConnecting}
          className={`
            w-20 h-20 rounded-full flex items-center justify-center
            transition-all duration-300 ease-in-out
            ${!isConnected ? 'bg-gray-200 cursor-not-allowed' : isRecording
              ? 'bg-red-100 hover:bg-red-200'
              : 'bg-indigo-100 hover:bg-indigo-200'
            }
            ${isRecording ? 'scale-110 shadow-lg' : 'scale-100 shadow'}
          `}
        >
          {isRecording ? (
            <StopCircle
              className={`
                h-10 w-10 text-red-500
                ${isRecording ? 'animate-pulse' : ''}
              `}
            />
          ) : (
            <Mic
              className={`
                h-10 w-10 text-indigo-600
              `}
            />
          )}
        </button>

        {/* Recording status */}
        <p className="mt-4 text-sm text-gray-600">
          {isRecording ? `Recording... (${messageCount} chunks sent)` : 'Ready to record'}
        </p>

        {/* Reconnect button */}
        {!isConnected && !isConnecting && (
          <button
            onClick={reconnect}
            className="mt-4 flex items-center text-blue-600 hover:text-blue-800 font-medium text-sm"
          >
            <RotateCcw className="h-4 w-4 mr-1" />
            Reconnect
          </button>
        )}
      </div>

      {/* Debug toggle */}
      <div className="mt-8 text-center">
        <button
          onClick={() => setDebugMode(!debugMode)}
          className="text-xs text-gray-500 underline"
        >
          {debugMode ? 'Hide Debug Info' : 'Show Debug Info'}
        </button>
      </div>

      {/* Debug log */}
      {debugMode && (
        <div className="mt-2 p-2 bg-gray-100 rounded text-xs font-mono h-48 overflow-y-auto">
          {debugLog.map((log, i) => (
            <div key={i} className="mb-1">{log}</div>
          ))}
          {debugLog.length === 0 && <div className="text-gray-500">No debug logs yet</div>}
        </div>
      )}

      {/* Instructions */}
      <div className="mt-4 border-t border-gray-100 pt-4">
        <h3 className="text-sm font-medium text-gray-700 mb-2">How it works:</h3>
        <ol className="text-xs text-gray-600 list-decimal list-inside space-y-1">
          <li>Press the microphone button to start recording</li>
          <li>Your audio will stream to the server in real-time</li>
          <li>Press the stop button when you're finished</li>
        </ol>
      </div>
    </div>
  );
};

export default AudioRecorder;