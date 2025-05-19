import React from 'react';
import { AlertCircle, CheckCircle, Loader } from 'lucide-react';

interface StatusIndicatorProps {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
}

const StatusIndicator: React.FC<StatusIndicatorProps> = ({ 
  isConnected, 
  isConnecting, 
  error 
}) => {
  return (
    <div className="flex flex-col items-center mt-4">
      <div className="flex items-center mb-1">
        {isConnecting ? (
          <>
            <Loader className="h-4 w-4 text-blue-500 animate-spin mr-2" />
            <span className="text-sm text-gray-600">Connecting to server...</span>
          </>
        ) : isConnected ? (
          <>
            <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
            <span className="text-sm text-gray-600">Connected to server</span>
          </>
        ) : (
          <>
            <AlertCircle className="h-4 w-4 text-red-500 mr-2" />
            <span className="text-sm text-gray-600">Disconnected from server</span>
          </>
        )}
      </div>
      
      {error && (
        <div className="text-xs text-red-500 mt-1">
          Error: {error}
        </div>
      )}
    </div>
  );
};

export default StatusIndicator;