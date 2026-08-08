import React, { useEffect, useState } from 'react';
import { Menu, ShieldCheck, Wifi, WifiOff } from 'lucide-react';
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

        {/*
          FT-071: a global search input used to sit here. It accepted typing
          but had no handler, no state and no endpoint - typing produced
          nothing at all. There is no global search API in the specification,
          so the control has been removed rather than left as decorative
          interactivity. Per-table search remains available and functional on
          every list page.
        */}
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

        {/*
          FT-071: a notifications bell used to sit here, permanently displaying
          an "unread" dot. It had no click handler, and the notifications API
          (GET /notifications/me) does not exist in this build - the dot could
          never correspond to anything. Showing a persistent unread indicator
          for a feature that cannot be opened is misleading, so the control has
          been removed. The capability is tracked as FT-068.
        */}

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

