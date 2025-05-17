import { useRef, useCallback } from 'react';

interface AudioPlayerHook {
  playAudio: (audioData: Uint8Array, onComplete?: () => void) => void;
}

export const useAudioPlayer = (): AudioPlayerHook => {
  const audioContextRef = useRef<AudioContext | null>(null);
  const synth = useRef<SpeechSynthesis | null>(null);
  
  // Function to play audio from Uint8Array
  const playAudio = useCallback((audioData: Uint8Array, onComplete?: () => void) => {
    console.log('Playing audio data, length:', audioData.length);
    
    // First try to interpret it as text (if it's a reasonable length for text)
    if (audioData.length < 2000) {
      try {
        const decoder = new TextDecoder();
        const text = decoder.decode(audioData).trim();
        
        console.log('Attempting to convert text to speech:', text);
        
        // If we have a non-empty string, use speech synthesis
        if (text && text.length > 0) {
          // Initialize speech synthesis if not already
          if (!synth.current) {
            synth.current = window.speechSynthesis;
          }
          
          // Create utterance
          const utterance = new SpeechSynthesisUtterance(text);
          
          // Set completion callback
          utterance.onend = () => {
            console.log('Speech synthesis complete');
            if (onComplete) onComplete();
          };
          
          // Set error handler
          utterance.onerror = (err) => {
            console.error('Speech synthesis error:', err);
            if (onComplete) onComplete();
          };
          
          // Speak the text
          synth.current.speak(utterance);
          return;
        }
      } catch (error) {
        console.warn('Error interpreting data as text, trying audio fallback:', error);
      }
    }
    
    // Fallback: Handle as audio data
    try {
      // Create audio context if it doesn't exist
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      }
      
      const audioContext = audioContextRef.current;
      
      // Create a buffer based on the audio data size
      const bufferSize = audioData.length;
      const audioBuffer = audioContext.createBuffer(1, bufferSize, audioContext.sampleRate);
      const channelData = audioBuffer.getChannelData(0);
      
      // Convert Uint8Array to float values between -1 and 1
      for (let i = 0; i < bufferSize; i++) {
        channelData[i] = (audioData[i] / 128.0) - 1.0;
      }
      
      // Create a buffer source and connect it to the destination
      const source = audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContext.destination);
      
      // Set up completion callback
      if (onComplete) {
        source.onended = onComplete;
      }
      
      // Play the audio
      source.start();
      console.log('Started playing raw audio');
      
    } catch (error) {
      console.error('Error playing audio:', error);
      
      // If both text and audio playback fail, just call the completion handler
      if (onComplete) {
        setTimeout(onComplete, 500);
      }
    }
  }, []);
  
  return { playAudio };
};