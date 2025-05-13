import React, { useState, useEffect, useRef } from 'react';
import { Mic, StopCircle, RotateCcw } from 'lucide-react';
import { useWebSocket } from '../contexts/WebSocketContext';
import AudioWaveform from './AudioWaveform';
import StatusIndicator from './StatusIndicator';

const AudioRecorder: React.FC = () => {
  // Recording state
  const [isRecording, setIsRecording] = useState(false);
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [audioData, setAudioData] = useState<Uint8Array | null>(null);
  
  // Audio processing refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataArrayRef = useRef<Uint8Array | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  
  // WebSocket context
  const { connected, connecting, connectionError, sendMessage, reconnect } = useWebSocket();
  
  // Request microphone permission on component mount
  useEffect(() => {
    const requestMicrophonePermission = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setHasPermission(true);
        setPermissionError(null);
        audioStreamRef.current = stream;
        
        // Set up audio analysis
        const audioContext = new AudioContext();
        audioContextRef.current = audioContext;
        const analyser = audioContext.createAnalyser();
        analyserRef.current = analyser;
        analyser.fftSize = 256;
        
        const source = audioContext.createMediaStreamSource(stream);
        source.connect(analyser);
        
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        dataArrayRef.current = dataArray;
        
        // Initial update of audio data
        updateAudioData();
        
        // Clean up function
        return () => {
          if (animationFrameRef.current) {
            cancelAnimationFrame(animationFrameRef.current);
          }
          
          if (audioStreamRef.current) {
            audioStreamRef.current.getTracks().forEach(track => track.stop());
          }
          
          if (audioContextRef.current) {
            audioContextRef.current.close();
          }
        };
      } catch (error) {
        console.error('Error accessing microphone:', error);
        setHasPermission(false);
        setPermissionError(
          error instanceof Error 
            ? error.message 
            : 'Unable to access your microphone. Please check permissions.'
        );
      }
    };

    requestMicrophonePermission();
  }, []);

  // Update audio data for visualization
  const updateAudioData = () => {
    if (!analyserRef.current || !dataArrayRef.current) return;
    
    analyserRef.current.getByteTimeDomainData(dataArrayRef.current);
    setAudioData(new Uint8Array(dataArrayRef.current));
    
    animationFrameRef.current = requestAnimationFrame(updateAudioData);
  };

  // Start recording
  const startRecording = () => {
    if (!audioStreamRef.current || !connected) return;
    
    try {
      // Create a processor script for raw audio processing
      const audioContext = audioContextRef.current;
      if (!audioContext) return;
      
      // Reset the recorder if it exists
      if (mediaRecorderRef.current) {
        mediaRecorderRef.current.stop();
      }
      
      // Configure audio context for 16-bit processing
      const processor = audioContext.createScriptProcessor(1024, 1, 1);
      const input = audioContext.createMediaStreamSource(audioStreamRef.current);
      
      processor.onaudioprocess = (event) => {
        if (!isRecording) return;
        
        // Get the raw audio data from the input buffer
        const inputBuffer = event.inputBuffer;
        const leftChannel = inputBuffer.getChannelData(0);
        
        // Convert to 16-bit PCM (Int16Array)
        const sampleLength = leftChannel.length;
        const buffer = new Int16Array(sampleLength);
        
        for (let i = 0; i < sampleLength; i++) {
          // Convert float32 [-1.0, 1.0] to int16 [-32768, 32767]
          const s = Math.max(-1, Math.min(1, leftChannel[i]));
          buffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        
        // Send the audio data via WebSocket
        if (connected) {
          sendMessage(buffer);
        }
      };
      
      // Connect the processor
      input.connect(processor);
      processor.connect(audioContext.destination);
      
      // Set up MediaRecorder for standard recording (backup)
      const mediaRecorder = new MediaRecorder(audioStreamRef.current);
      mediaRecorderRef.current = mediaRecorder;
      
      mediaRecorder.start(100); // Send in 100ms chunks
      setIsRecording(true);
      
      // Clean up the processor when stopping
      return () => {
        input.disconnect(processor);
        processor.disconnect(audioContext.destination);
      };
    } catch (error) {
      console.error('Error starting recording:', error);
      setPermissionError('Failed to start recording. Please try again.');
    }
  };

  // Stop recording
  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    
    setIsRecording(false);
  };

  // Toggle recording
  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  return (
    <div className="w-full max-w-md mx-auto bg-white rounded-xl shadow-md overflow-hidden p-6">
      <h2 className="text-2xl font-semibold text-gray-800 text-center mb-6">
        Voice Recording
      </h2>
      
      {/* Audio visualization */}
      <AudioWaveform audioData={audioData} isRecording={isRecording} />
      
      {/* Status indicator */}
      <StatusIndicator 
        isConnected={connected} 
        isConnecting={connecting} 
        error={connectionError || permissionError} 
      />
      
      {/* Recording controls */}
      <div className="mt-8 flex flex-col items-center">
        {hasPermission === false ? (
          <div className="text-center text-red-500 mb-4">
            <p>Microphone access denied.</p>
            <p className="text-sm mt-2">Please allow microphone access in your browser settings.</p>
          </div>
        ) : (
          <>
            {/* Main record button */}
            <button
              onClick={toggleRecording}
              disabled={!connected || hasPermission === false}
              className={`
                w-20 h-20 rounded-full flex items-center justify-center
                transition-all duration-300 ease-in-out
                ${!connected ? 'bg-gray-200 cursor-not-allowed' : isRecording 
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
              {isRecording ? 'Recording...' : 'Ready to record'}
            </p>
            
            {/* Reconnect button */}
            {!connected && !connecting && (
              <button
                onClick={reconnect}
                className="mt-4 flex items-center text-blue-600 hover:text-blue-800 font-medium text-sm"
              >
                <RotateCcw className="h-4 w-4 mr-1" />
                Reconnect
              </button>
            )}
          </>
        )}
      </div>
      
      {/* Instructions */}
      <div className="mt-8 border-t border-gray-100 pt-4">
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