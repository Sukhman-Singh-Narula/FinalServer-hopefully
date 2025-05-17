import React from 'react';
import { Mic } from 'lucide-react';

const Header: React.FC = () => {
  return (
    <header className="bg-white shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <Mic className="h-8 w-8 text-indigo-600" strokeWidth={1.5} />
            <h1 className="ml-2 text-xl font-medium text-gray-900">Voice AI</h1>
          </div>
          <div className="text-sm text-gray-600">Simple. Powerful. Secure.</div>
        </div>
      </div>
    </header>
  );
};

export default Header;