// Audio streaming types
export interface AudioStreamOptions {
  sampleRate: number;
  channels: number;
  bitDepth: number;
}

export interface WebSocketMessage {
  type: 'audio' | 'text' | 'control';
  data: Uint8Array | string;
}

// Application state types
export type ConversationState = 'idle' | 'listening' | 'processing' | 'responding' | 'error';

export interface AudioVisualizerProps {
  audioAnalyser: AnalyserNode;
}