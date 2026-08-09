import React, { useEffect, useId } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  children: React.ReactNode;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  size = 'md',
  children,
}) => {
  const titleId = useId();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const sizeClasses = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-space-4 bg-primary/40 backdrop-blur-xs transition-opacity duration-200"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`bg-surface border border-surface-container-highest rounded-2xl w-full ${sizeClasses[size]} overflow-hidden shadow-2xl transition-all transform scale-100 animate-in fade-in-0 zoom-in-95 duration-200`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-space-6 py-space-5 border-b border-surface-container-highest flex items-center justify-between bg-surface-container-low/50">
          <div>
            <h3 id={titleId} className="font-headline-md text-headline-md text-primary font-bold">{title}</h3>
            {subtitle && <p className="font-caption text-xs text-on-surface-variant mt-0.5">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            className="text-on-surface-variant hover:text-on-surface p-space-1.5 rounded-lg hover:bg-surface-container transition-colors cursor-pointer focus:outline-none focus:ring-1 focus:ring-primary-container"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-space-6 max-h-[80vh] overflow-y-auto">{children}</div>
      </div>
    </div>
  );
};
