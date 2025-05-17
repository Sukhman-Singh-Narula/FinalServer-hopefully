import React, { useEffect, useRef } from 'react';

interface AudioVisualizerProps {
  audioAnalyser: AnalyserNode;
}

const AudioVisualizer: React.FC<AudioVisualizerProps> = ({ audioAnalyser }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>(0);

  useEffect(() => {
    if (!canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set up the analyser
    audioAnalyser.fftSize = 256;
    const bufferLength = audioAnalyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    // Set canvas dimensions
    const resize = () => {
      canvas.width = canvas.clientWidth * window.devicePixelRatio;
      canvas.height = canvas.clientHeight * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };
    
    resize();
    window.addEventListener('resize', resize);

    // Animation function
    const draw = () => {
      animationRef.current = requestAnimationFrame(draw);

      // Get the frequency data
      audioAnalyser.getByteFrequencyData(dataArray);

      // Clear the canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw the visualization
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      const barWidth = width / bufferLength * 2.5;
      let x = 0;
      
      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * height / 1.2;
        
        // Create gradient for each bar
        const gradient = ctx.createLinearGradient(0, height - barHeight, 0, height);
        gradient.addColorStop(0, 'rgba(59, 130, 246, 0.8)');  // blue-500
        gradient.addColorStop(1, 'rgba(96, 165, 250, 0.4)');  // blue-400
        
        ctx.fillStyle = gradient;
        ctx.fillRect(x, height - barHeight, barWidth, barHeight);
        
        // Draw a rounded top on each bar
        ctx.beginPath();
        ctx.arc(x + barWidth / 2, height - barHeight, barWidth / 2, 0, Math.PI, true);
        ctx.fillStyle = 'rgba(59, 130, 246, 0.8)';
        ctx.fill();
        
        x += barWidth + 1;
      }
    };

    // Start animation
    draw();

    // Cleanup
    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animationRef.current);
    };
  }, [audioAnalyser]);

  return (
    <canvas 
      ref={canvasRef} 
      className="w-full h-full rounded-lg"
    />
  );
};

export default AudioVisualizer;