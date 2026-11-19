import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  CalendarClock,
  Building2,
  CalendarCheck,
  CalendarDays,
  Globe2,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  ShieldCheck,
  Wallet,
  ClipboardList,
  SearchCheck,
  Camera,
  Link2,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { canViewAdmin, isAccountant, resolveRole } from '../../utils/roles';

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen = false, onClose }) => {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  // Admin pages are visible to administrators and the accountant (the accountant mostly reads).
  const userIsAdmin = canViewAdmin(user);
  const visitPlanningPath = userIsAdmin ? '/admin/visit-planning' : '/visit-planning';

  const navItems = [
    { name: 'Dashboard',            path: '/',          icon: LayoutDashboard, roles: ['ADMIN', 'EMPLOYEE'] },
    { name: 'Visit Planning',       path: visitPlanningPath, icon: CalendarDays, roles: ['ADMIN', 'EMPLOYEE'] },
    { name: 'Employees',            path: '/employees', icon: Users,           roles: ['ADMIN'] },
    { name: 'Employee Daily Logs',  path: '/daily-logs',icon: CalendarClock,   roles: ['ADMIN'] },
    { name: 'Territories',          path: '/territories', icon: Globe2,        roles: ['ADMIN'] },
    { name: 'Customers',            path: '/customers', icon: Building2,       roles: ['ADMIN'] },
    { name: 'Outlet Verification',  path: '/customers/outlet-verification', icon: Camera, roles: ['ADMIN'] },
    { name: 'Outlet Mapping',       path: '/customers/outlet-mapping', icon: Link2, roles: ['ADMIN'] },
    { name: 'Visits',               path: '/visits',    icon: CalendarCheck,   roles: ['ADMIN', 'EMPLOYEE'] },
    { name: 'Ad-hoc Review',        path: '/visits/adhoc-review', icon: SearchCheck, roles: ['ADMIN'] },
    { name: 'Map',                  path: '/map',       icon: Globe2,          roles: ['ADMIN'] },
    { name: 'Customer Requirements',path: '/requirements', icon: ClipboardList, roles: ['ADMIN'] },
    { name: 'Requirement Forms',    path: '/forms',     icon: FileText,        roles: ['ADMIN'] },
    { name: 'Payment Collections',  path: '/payments',  icon: Wallet,          roles: ['ADMIN'] },
    { name: 'Reports & Collections',path: '/reports',   icon: BarChart3,       roles: ['ADMIN'] },
  ];

  const visibleNavItems = navItems.filter((item) => {
    // Least privilege: no/unknown role sees nothing beyond the EMPLOYEE set. A Super Admin sees
    // everything an Admin sees (nav items are declared per ADMIN/EMPLOYEE tier).
    const tier = userIsAdmin ? 'ADMIN' : resolveRole(user?.role);
    return item.roles.includes(tier);
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
            {isAccountant(user) ? 'Accountant' : userIsAdmin ? 'Admin Dashboard' : 'Employee Portal'}
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
                  isActive &&
                  !(item.path === '/visits' && pathname.startsWith('/visits/adhoc-review')) &&
                  !(item.path === '/customers' &&
                    (pathname.startsWith('/customers/outlet-verification') || pathname.startsWith('/customers/outlet-mapping')))
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
          {userIsAdmin && (
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

          <NavLink
            to="/profile"
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center gap-space-2 px-space-3 py-space-2 rounded-lg border transition-colors ${
                isActive
                  ? 'bg-primary-container text-secondary-container border-secondary-container'
                  : 'bg-surface-container-low hover:bg-surface-container border-outline-variant'
              }`
            }
          >
            <div className="w-8 h-8 rounded-full bg-primary-fixed text-on-primary-fixed flex items-center justify-center font-headline-sm text-headline-sm uppercase shrink-0">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="truncate min-w-0 flex-1">
              <p className="font-label-md text-label-md text-on-surface truncate">{user?.full_name || user?.email?.split('@')[0] || 'User'}</p>
              <p className="text-[11px] text-on-surface-variant font-caption truncate">{user?.email}</p>
            </div>
          </NavLink>

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
