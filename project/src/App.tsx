import React from 'react';
import Header from './components/Header';
import AudioRecorder from './components/AudioRecorder';
import { WebSocketProvider } from './contexts/WebSocketContext';

function App() {
  return (
    <WebSocketProvider>
      <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center p-4">
          <AudioRecorder />
        </main>
        <footer className="text-center text-gray-500 text-sm py-4">
          <p>© {new Date().getFullYear()} AI Voice Assistant</p>
        </footer>
      </div>
    </WebSocketProvider>
  );
}

export default App;