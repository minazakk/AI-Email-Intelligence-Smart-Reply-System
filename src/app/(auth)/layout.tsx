'use client';

import { ReactNode } from 'react';

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-gray-900">AI Email Intelligence</h1>
            <p className="text-gray-500 mt-1">Smart email management with AI</p>
          </div>
          {children}
        </div>
        <p className="text-center text-sm text-gray-500 mt-6">
          Demo: demo@example.com / DemoPassw0rd!
        </p>
      </div>
    </div>
  );
}