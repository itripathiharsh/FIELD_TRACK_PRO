import React, { useState } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useAuth } from '../../context/AuthContext';

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center text-on-surface">
        <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin"></div>
        <p className="mt-space-4 font-caption text-caption text-on-surface-variant">
          Initializing FieldTrack Pro Subsystem...
        </p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <div className="min-h-screen bg-background text-on-surface">{children}</div>;
  }

  return (
    <div className="min-h-screen bg-background text-on-background font-body-md flex antialiased relative">
      {/* Sidebar navigation */}
      <Sidebar isOpen={isMobileMenuOpen} onClose={() => setIsMobileMenuOpen(false)} />

      {/* Main Content Area */}
      <div className="flex-1 ml-0 md:ml-[240px] flex flex-col min-h-screen min-w-0">
        <Header onMobileMenuToggle={() => setIsMobileMenuOpen(!isMobileMenuOpen)} />
        <main className="p-space-4 md:p-space-8 flex-1 max-w-[1440px] w-full mx-auto">{children}</main>
      </div>
    </div>
  );
};

