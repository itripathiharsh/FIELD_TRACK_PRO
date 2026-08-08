import React, { useEffect, useState } from 'react';
import { Menu, Bell, ShieldCheck, Wifi, WifiOff, Search } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { apiClient } from '../../api/client';

interface HeaderProps {
  onMobileMenuToggle: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onMobileMenuToggle }) => {
  const { user } = useAuth();
  const [isHealthy, setIsHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    apiClient
      .getHealth()
      .then((data: { status: string }) => setIsHealthy(data.status === 'ok' || data.status === 'UP' || data.status === 'healthy'))
      .catch(() => setIsHealthy(false));
  }, []);

  return (
    <header className="h-[64px] bg-surface border-b border-surface-container-highest px-space-6 flex items-center justify-between sticky top-0 z-30 shadow-2xs">
      <div className="flex items-center gap-space-4">
        <button
          onClick={onMobileMenuToggle}
          className="p-space-2 text-on-surface-variant hover:text-on-surface hover:bg-surface-container rounded-lg md:hidden transition-colors"
          aria-label="Toggle Navigation Menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        {/* Global Quick Search Input */}
        <div className="relative hidden sm:block">
          <Search className="w-4 h-4 text-outline absolute left-space-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            placeholder="Search telemetry, reps, visits..."
            className="bg-surface-container-low border border-outline-variant rounded-lg pl-space-8 pr-space-4 py-space-1.5 text-on-surface font-body text-body-md placeholder:text-text-muted focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container w-64 md:w-80 transition-all"
          />
        </div>
      </div>

      <div className="flex items-center gap-space-4">
        {/* Backend API Telemetry Health Indicator */}
        <div className="flex items-center gap-space-2 px-space-3 py-space-1 bg-surface-container-low border border-outline-variant rounded-full text-label-md font-label-md">
          {isHealthy === null ? (
            <span className="w-2 h-2 rounded-full bg-outline animate-pulse" />
          ) : isHealthy ? (
            <>
              <Wifi className="w-3.5 h-3.5 text-secondary" />
              <span className="text-on-surface text-[12px]">API Online</span>
            </>
          ) : (
            <>
              <WifiOff className="w-3.5 h-3.5 text-error" />
              <span className="text-error text-[12px]">API Offline</span>
            </>
          )}
        </div>

        {/* Notifications Icon */}
        <button
          className="p-space-2 text-on-surface-variant hover:text-on-surface hover:bg-surface-container rounded-lg relative transition-colors"
          aria-label="Notifications"
        >
          <Bell className="w-5 h-5" />
          <span className="w-2 h-2 rounded-full bg-secondary-container absolute top-1.5 right-1.5" />
        </button>

        {/* User Role Badge */}
        <div className="hidden lg:flex items-center gap-space-2 pl-space-2 border-l border-surface-container-highest">
          <ShieldCheck className="w-4 h-4 text-primary" />
          <span className="font-label-md text-label-md uppercase text-on-surface-variant bg-primary-fixed border border-primary-fixed-dim px-space-2 py-space-1 rounded-md">
            {user?.role || 'User'}
          </span>
        </div>
      </div>
    </header>
  );
};
