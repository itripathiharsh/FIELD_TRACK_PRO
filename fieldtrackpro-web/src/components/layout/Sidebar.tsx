import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Map,
  Building2,
  CalendarCheck,
  MapPin,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  ShieldCheck,
  Wallet,
  UploadCloud
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen = false, onClose }) => {
  const { user, logout } = useAuth();
  const isEmployee = user?.role === 'EMPLOYEE';

  const navItems = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard, roles: ['ADMIN', 'MANAGER', 'EMPLOYEE'] },
    { name: 'Employees', path: '/employees', icon: Users, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Territories', path: '/territories', icon: Map, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Customers', path: '/customers', icon: Building2, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Visits', path: '/visits', icon: CalendarCheck, roles: ['ADMIN', 'MANAGER', 'EMPLOYEE'] },
    { name: 'Map', path: '/map', icon: MapPin, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Geo Logs', path: '/geo-logs', icon: MapPin, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Requirement Forms', path: '/forms', icon: FileText, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Payment Collections', path: '/payments', icon: Wallet, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Excel / MIS Import', path: '/imports', icon: UploadCloud, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Reports', path: '/reports', icon: BarChart3, roles: ['ADMIN', 'MANAGER'] },
  ];

  const visibleNavItems = navItems.filter((item) => {
    if (!user?.role) return item.roles.includes('ADMIN');
    return item.roles.includes(user.role);
  });

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 bg-on-surface/40 backdrop-blur-xs z-40 md:hidden"
        />
      )}

      <aside
        className={`w-[240px] h-screen fixed left-0 top-0 bg-surface shadow-sm flex flex-col py-space-6 px-space-4 z-40 border-r border-surface-container-highest shrink-0 transition-transform duration-200 ease-in-out ${
          isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        {/* Brand Header */}
        <div className="mb-space-6 px-space-2 flex flex-col items-start border-b border-surface-container-highest pb-space-4">
          <div className="flex items-center gap-space-2 mb-space-1">
            <div className="w-8 h-8 bg-primary-container rounded flex items-center justify-center text-secondary-container">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h1 className="font-headline-md text-headline-md text-primary tracking-tight">FieldTrack Pro</h1>
          </div>
          <p className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">
            {isEmployee ? 'Employee Portal' : 'Admin Dashboard'}
          </p>
        </div>

        {/* Navigation Menu */}
        <nav className="flex-1 flex flex-col gap-space-1 overflow-y-auto font-nav-link text-nav-link">
          {visibleNavItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-space-3 px-space-3 py-space-2 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-primary-container text-secondary-container font-headline-sm border-r-4 border-secondary-container opacity-95 shadow-xs'
                    : 'text-on-surface-variant hover:bg-surface-container'
                }`
              }
            >
              <item.icon className="w-4 h-4 shrink-0" />
              <span>{item.name}</span>
            </NavLink>
          ))}
        </nav>

        {/* Bottom Tabs & User Profile */}
        <div className="mt-auto pt-space-4 border-t border-surface-container-highest flex flex-col gap-space-2">
          {user?.role === 'ADMIN' && (
            <NavLink
              to="/settings"
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-space-3 px-space-3 py-space-2 rounded-lg font-nav-link text-nav-link transition-colors ${
                  isActive
                    ? 'bg-primary-container text-secondary-container font-headline-sm border-r-4 border-secondary-container'
                    : 'text-on-surface-variant hover:bg-surface-container'
                }`
              }
            >
              <Settings className="w-4 h-4 shrink-0" />
              <span>Settings</span>
            </NavLink>
          )}

          <div className="flex items-center gap-space-2 px-space-3 py-space-2 bg-surface-container-low rounded-lg border border-outline-variant">
            <div className="w-8 h-8 rounded-full bg-primary-fixed text-on-primary-fixed flex items-center justify-center font-headline-sm text-headline-sm uppercase shrink-0">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="truncate min-w-0 flex-1">
              <p className="font-label-md text-label-md text-on-surface truncate">{user?.full_name || user?.email?.split('@')[0] || 'User'}</p>
              <p className="text-[11px] text-on-surface-variant font-caption truncate">{user?.email}</p>
            </div>
          </div>

          <button
            onClick={() => void logout()}
            className="flex items-center gap-space-3 px-space-3 py-space-2 rounded-lg text-error font-button text-button uppercase hover:bg-error-tint transition-colors w-full"
          >
            <LogOut className="w-4 h-4 shrink-0" />
            <span>Logout</span>
          </button>
        </div>
      </aside>
    </>
  );
};
