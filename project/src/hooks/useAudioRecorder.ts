import { useState, useEffect, useRef, useCallback } from 'react';

interface AudioRecorderHook {
  isRecording: boolean;
  startRecording: () => void;
  stopRecording: () => void;
  audioData: Uint8Array | null;
  audioAnalyser: AnalyserNode | null;
  hasPermission: boolean;
  permissionError: string | null;
  requestPermission: () => Promise<boolean>;
}

export const useAudioRecorder = (): AudioRecorderHook => {
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [audioData, setAudioData] = useState<Uint8Array | null>(null);
  const [hasPermission, setHasPermission] = useState<boolean>(false);
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [audioAnalyser, setAudioAnalyser] = useState<AnalyserNode | null>(null);
  
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const microphoneSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  const cleanupAudio = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    
    if (microphoneSourceRef.current) {
      microphoneSourceRef.current.disconnect();
      microphoneSourceRef.current = null;
    }
    
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }
    
    if (audioContextRef.current) {
      if (audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close();
      }
      audioContextRef.current = null;
    }
    
    setAudioAnalyser(null);
  }, []);

  const requestPermission = useCallback(async (): Promise<boolean> => {
    try {
      setPermissionError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(track => track.stop());
      setHasPermission(true);
      return true;
    } catch (error) {
      let errorMessage = 'An unknown error occurred while requesting microphone access';
      
      if (error instanceof Error) {
        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
          errorMessage = 'Microphone access was denied. Please allow microphone access in your browser settings and try again.';
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
          errorMessage = 'No microphone found. Please ensure a microphone is connected and try again.';
        } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
          errorMessage = 'Could not access your microphone. It may be in use by another application.';
        }
      }
      
      setPermissionError(errorMessage);
      setHasPermission(false);
      return false;
    }
  }, []);

  const startRecording = useCallback(() => {
    if (isRecording) return;

    const initializeAudio = async () => {
      try {
        setPermissionError(null);
        const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
          sampleRate: 16000,
        });
        audioContextRef.current = audioContext;
        
        const stream = await navigator.mediaDevices.getUserMedia({ 
          audio: { 
            channelCount: 1,
            sampleRate: 16000,
            echoCancellation: true,
            noiseSuppression: true,
          } 
        });
        mediaStreamRef.current = stream;
        
        const microphoneSource = audioContext.createMediaStreamSource(stream);
        microphoneSourceRef.current = microphoneSource;
        
        const analyser = audioContext.createAnalyser();
        analyser.smoothingTimeConstant = 0.8;
        microphoneSource.connect(analyser);
        setAudioAnalyser(analyser);
        
        const processor = audioContext.createScriptProcessor(2048, 1, 1);
        processorRef.current = processor;
        
        microphoneSource.connect(processor);
        processor.connect(audioContext.destination);
        
        processor.onaudioprocess = (e) => {
          if (!isRecording) return;
          
          const inputBuffer = e.inputBuffer.getChannelData(0);
          const pcmData = new Int16Array(inputBuffer.length);
          for (let i = 0; i < inputBuffer.length; i++) {
            const s = Math.max(-1, Math.min(1, inputBuffer[i]));
            pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }
          
          const uint8Data = new Uint8Array(pcmData.buffer);
          setAudioData(uint8Data);
        };
        
        setHasPermission(true);
        setIsRecording(true);
      } catch (error) {
        console.error('Error starting recording:', error);
        cleanupAudio();
        
        if (error instanceof Error) {
          setPermissionError(
            error.name === 'NotAllowedError' 
              ? 'Microphone access was denied. Please allow microphone access in your browser settings and try again.'
              : `Error accessing microphone: ${error.message}`
          );
        }
        setHasPermission(false);
      }
    };

    initializeAudio();
  }, [isRecording, cleanupAudio]);

  const stopRecording = useCallback(() => {
    if (!isRecording) return;
    
    setIsRecording(false);
    cleanupAudio();
  }, [isRecording, cleanupAudio]);

  useEffect(() => {
    return () => {
      if (isRecording) {
        cleanupAudio();
      }
    };
  }, [isRecording, cleanupAudio]);

  return {
    isRecording,
    startRecording,
    stopRecording,
    audioData,
    audioAnalyser,
    hasPermission,
    permissionError,
    requestPermission,
  };
};