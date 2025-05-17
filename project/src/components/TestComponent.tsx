import React, { useState } from 'react';
import { Mic, MicOff } from 'lucide-react';

const TestComponent: React.FC = () => {
  const [isActive, setIsActive] = useState(false);
  
  return (
    <div className="bg-white rounded-2xl shadow-lg p-6">
      <div className="flex flex-col items-center">
        <div className="w-48 h-48 rounded-full flex items-center justify-center bg-gray-100 mb-6">
          {isActive ? (
            <Mic className="h-12 w-12 text-blue-500 animate-pulse" />
          ) : (
            <MicOff className="h-12 w-12 text-gray-500" />
          )}
        </div>
        
        <p className="text-gray-700 mb-6">
          {isActive ? 'Microphone is active' : 'Microphone is inactive'}
        </p>
        
        <button
          onClick={() => setIsActive(!isActive)}
          className={`px-8 py-4 rounded-full font-medium text-white transition-all duration-300 ${
            isActive ? 'bg-red-500 hover:bg-red-600' : 'bg-blue-500 hover:bg-blue-600'
          }`}
        >
          {isActive ? 'Stop Microphone' : 'Start Microphone'}
        </button>
      </div>
    </div>
  );
};

export default TestComponent;