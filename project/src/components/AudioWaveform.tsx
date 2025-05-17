import React, { useRef, useEffect } from 'react';

interface AudioWaveformProps {
  audioData: Uint8Array | null;
  isRecording: boolean;
}

const AudioWaveform: React.FC<AudioWaveformProps> = ({ audioData, isRecording }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Draw the waveform
  useEffect(() => {
    if (!canvasRef.current || !audioData) return;
    
    const canvas = canvasRef.current;
    const context = canvas.getContext('2d');
    if (!context) return;
    
    // Get canvas dimensions
    const width = canvas.width;
    const height = canvas.height;
    
    // Clear the canvas
    context.clearRect(0, 0, width, height);
    
    // Draw waveform
    const sliceWidth = width / audioData.length;
    let x = 0;
    
    context.beginPath();
    context.lineWidth = 2;
    context.strokeStyle = isRecording ? '#4F46E5' : '#94A3B8'; // Indigo when recording, light gray when idle
    
    // Start from the middle of the canvas
    context.moveTo(0, height / 2);
    
    for (let i = 0; i < audioData.length; i++) {
      const v = audioData[i] / 128.0; // Convert to a scale of 0-2
      const y = (v * height) / 2;
      
      if (i === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
      
      x += sliceWidth;
    }
    
    // Ensure the line goes to the end of the canvas
    context.lineTo(width, height / 2);
    context.stroke();
    
    // If not recording, add a gentle pulse animation
    if (!isRecording) {
      const time = Date.now() / 1000;
      const amplitude = Math.sin(time * 2) * 10 + 20; // Gentle pulse
      
      context.beginPath();
      context.strokeStyle = '#CBD5E1';
      context.lineWidth = 1;
      
      for (let i = 0; i < width; i += 5) {
        const y = Math.sin(i / 20 + time * 3) * amplitude + height / 2;
        if (i === 0) {
          context.moveTo(i, y);
        } else {
          context.lineTo(i, y);
        }
      }
      
      context.stroke();
    }
  }, [audioData, isRecording]);

  return (
    <div className="w-full h-24 bg-white rounded-lg shadow-sm overflow-hidden">
      <canvas
        ref={canvasRef}
        width={300}
        height={100}
        className="w-full h-full"
      />
    </div>
  );
};

export default AudioWaveform;