import React from 'react';
import { Toaster } from 'react-hot-toast';
import Sidebar from './Sidebar';

interface AppShellProps {
  children: React.ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-content" id="main-content">
        {children}
      </main>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#162035',
            color: '#F0F4FF',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: '10px',
            fontSize: '13px',
            fontFamily: 'Inter, sans-serif',
          },
          success: {
            iconTheme: { primary: '#10B981', secondary: '#F0F4FF' },
          },
          error: {
            iconTheme: { primary: '#EF4444', secondary: '#F0F4FF' },
          },
        }}
      />
    </div>
  );
}
