/**
 * Utility functions for audio processing
 */

// Convert Float32Array to Int16Array for raw audio transmission
export const convertToInt16 = (buffer: Float32Array): Int16Array => {
  const length = buffer.length;
  const result = new Int16Array(length);
  
  for (let i = 0; i < length; i++) {
    // Convert float32 [-1.0, 1.0] to int16 [-32768, 32767]
    const s = Math.max(-1, Math.min(1, buffer[i]));
    result[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  
  return result;
};

// Calculate audio level for visualization
export const calculateAudioLevel = (buffer: Uint8Array): number => {
  let sum = 0;
  const length = buffer.length;
  
  for (let i = 0; i < length; i++) {
    sum += Math.abs(buffer[i] - 128);
  }
  
  return sum / length / 128;
};

// Debounce function to limit the frequency of function calls
export const debounce = <T extends (...args: any[]) => any>(
  func: T,
  wait: number
): ((...args: Parameters<T>) => void) => {
  let timeout: ReturnType<typeof setTimeout> | null = null;
  
  return (...args: Parameters<T>): void => {
    if (timeout) {
      clearTimeout(timeout);
    }
    
    timeout = setTimeout(() => {
      func(...args);
    }, wait);
  };
};