import React, { useEffect, useRef, useState } from 'react';
import {
  Bell,
  AlertTriangle,
  Calendar,
  XCircle,
  CheckCheck,
  Check,
  Clock,
  Info,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { NotificationItem, NotificationType } from '../../types';

export const NotificationBell: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = async () => {
    try {
      const res = await apiClient.getUnreadNotificationCount();
      setUnreadCount(res.unread_count);
    } catch {
      // Non-blocking telemetry
    }
  };

  const fetchNotifications = async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.getMyNotifications();
      setNotifications(data);
      const unread = data.filter((n) => !n.is_read).length;
      setUnreadCount(unread);
    } catch {
      // Non-blocking
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchNotifications();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const handleMarkAsRead = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await apiClient.markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      // Silent error handling
    }
  };

  const handleMarkAllAsRead = async () => {
    try {
      await apiClient.markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // Silent error handling
    }
  };

  const getNotificationIcon = (type: NotificationType) => {
    switch (type) {
      case 'PLANNED_VISIT_MISSED':
        return <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />;
      case 'PLANNED_VISIT_CANCELLED':
        return <XCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />;
      case 'EMPLOYEE_SCHEDULE_CHANGED':
      case 'RESCHEDULED':
        return <Calendar className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />;
      default:
        return <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />;
    }
  };

  const formatTimestamp = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="relative p-2 text-on-surface-variant hover:text-on-surface hover:bg-surface-container rounded-lg transition-colors cursor-pointer"
        aria-label="Notifications"
        aria-expanded={isOpen}
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 min-w-[18px] h-[18px] px-1 bg-amber-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center animate-in zoom-in duration-200">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-surface border border-outline-variant rounded-2xl shadow-xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="p-3.5 px-4 bg-surface-container-low border-b border-outline-variant/60 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-headline-sm text-sm font-bold text-on-surface">Notifications</span>
              {unreadCount > 0 && (
                <span className="px-1.5 py-0.5 text-[11px] font-bold rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
                  {unreadCount} new
                </span>
              )}
            </div>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllAsRead}
                className="text-xs font-semibold text-primary hover:text-primary-hover flex items-center gap-1 transition-colors cursor-pointer"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-[380px] overflow-y-auto divide-y divide-outline-variant/30">
            {isLoading ? (
              <div className="p-8 text-center text-xs text-on-surface-variant flex flex-col items-center gap-2">
                <Clock className="w-5 h-5 animate-spin text-primary" />
                Loading notifications...
              </div>
            ) : notifications.length === 0 ? (
              <div className="p-8 text-center text-xs text-on-surface-variant flex flex-col items-center gap-2">
                <Bell className="w-6 h-6 text-on-surface-variant/40" />
                <span>No notifications yet.</span>
              </div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className={`p-3.5 px-4 flex items-start gap-3 transition-colors ${
                    !n.is_read
                      ? 'bg-amber-500/5 hover:bg-amber-500/10'
                      : 'hover:bg-surface-container'
                  }`}
                >
                  {getNotificationIcon(n.type)}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <p className="text-xs font-bold text-on-surface truncate">
                        {n.title || n.type.replace(/_/g, ' ')}
                      </p>
                      <span className="text-[10px] text-on-surface-variant/80 shrink-0">
                        {formatTimestamp(n.sent_at)}
                      </span>
                    </div>
                    <p className="text-xs text-on-surface-variant mt-0.5 line-clamp-2 leading-relaxed">
                      {n.message}
                    </p>
                  </div>
                  {!n.is_read && (
                    <button
                      onClick={(e) => handleMarkAsRead(n.id, e)}
                      title="Mark as read"
                      className="p-1 text-on-surface-variant hover:text-primary hover:bg-surface-container-high rounded transition-colors cursor-pointer"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
