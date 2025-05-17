<<<<<<< HEAD
import React, { useState } from 'react';
import TestComponent from './components/TestComponent';
import ConversationInterface from './components/ConversationInterface';
import DebugPanel from './components/DebugPanel';

function App() {
  const [useTestComponent, setUseTestComponent] = useState(true);
  
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <header className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Voice Chat</h1>
          <p className="text-gray-600">Start a conversation with your AI assistant</p>
        </header>
        
        {useTestComponent ? (
          <>
            <TestComponent />
            <div className="mt-4 text-center">
              <button 
                onClick={() => setUseTestComponent(false)}
                className="text-blue-500 underline"
              >
                Switch to full conversation interface
              </button>
            </div>
          </>
        ) : (
          <>
            <ConversationInterface />
            <div className="mt-4 text-center">
              <button 
                onClick={() => setUseTestComponent(true)}
                className="text-blue-500 underline"
              >
                Switch to simple test component
              </button>
            </div>
          </>
        )}
      </div>
      
      {/* Debug Panel */}
      <DebugPanel />
    </div>
=======
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
>>>>>>> e12212dfdbe338639139297619e8feb462c7dfaf
  );
}

export default App;