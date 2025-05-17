import React, { useEffect, useState } from 'react';

const DebugPanel: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [showPanel, setShowPanel] = useState(false);
  
  useEffect(() => {
    // Capture console logs
    const originalConsoleLog = console.log;
    const originalConsoleError = console.error;
    const originalConsoleWarn = console.warn;
    
    console.log = (...args) => {
      const message = args.map(arg => 
        typeof arg === 'object' ? JSON.stringify(arg, null, 2) : String(arg)
      ).join(' ');
      
      setLogs(prev => [...prev, `LOG: ${message}`].slice(-50));
      originalConsoleLog(...args);
    };
    
    console.error = (...args) => {
      const message = args.map(arg => 
        typeof arg === 'object' ? JSON.stringify(arg, null, 2) : String(arg)
      ).join(' ');
      
      setErrors(prev => [...prev, `ERROR: ${message}`].slice(-50));
      originalConsoleError(...args);
    };
    
    console.warn = (...args) => {
      const message = args.map(arg => 
        typeof arg === 'object' ? JSON.stringify(arg, null, 2) : String(arg)
      ).join(' ');
      
      setLogs(prev => [...prev, `WARN: ${message}`].slice(-50));
      originalConsoleWarn(...args);
    };
    
    // Test browser support for required APIs
    const apiTests = [
      { name: 'AudioContext', supported: 'AudioContext' in window || 'webkitAudioContext' in window },
      { name: 'getUserMedia', supported: navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function' },
      { name: 'WebSocket', supported: 'WebSocket' in window },
      { name: 'ScriptProcessorNode', supported: window.AudioContext && 'createScriptProcessor' in AudioContext.prototype }
    ];
    
    apiTests.forEach(test => {
      console.log(`API check: ${test.name} is ${test.supported ? 'supported' : 'NOT SUPPORTED'}`);
    });
    
    return () => {
      console.log = originalConsoleLog;
      console.error = originalConsoleError;
      console.warn = originalConsoleWarn;
    };
  }, []);
  
  return (
    <div className="fixed bottom-0 right-0 p-2 z-50">
      <button
        onClick={() => setShowPanel(!showPanel)}
        className="bg-gray-800 text-white px-3 py-1 rounded-md text-sm font-medium"
      >
        {showPanel ? 'Hide Debug' : 'Show Debug'}
      </button>
      
      {showPanel && (
        <div className="bg-gray-800 bg-opacity-90 text-white p-4 mt-2 rounded-lg w-96 max-h-96 overflow-auto">
          <div className="mb-4">
            <h3 className="font-bold mb-2">Errors ({errors.length})</h3>
            {errors.length === 0 ? (
              <p className="text-green-400">No errors detected</p>
            ) : (
              <div className="text-red-400 text-xs font-mono whitespace-pre-wrap">
                {errors.map((error, i) => (
                  <div key={i} className="mb-1 border-b border-gray-700 pb-1">
                    {error}
                  </div>
                ))}
              </div>
            )}
          </div>
          
          <div>
            <h3 className="font-bold mb-2">Logs</h3>
            <div className="text-gray-300 text-xs font-mono whitespace-pre-wrap">
              {logs.map((log, i) => (
                <div key={i} className="mb-1 border-b border-gray-700 pb-1">
                  {log}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DebugPanel;