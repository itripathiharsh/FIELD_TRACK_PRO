import React, { useState, useEffect } from 'react';
import { Tag, X, Plus, AlertCircle, Loader2 } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Brand } from '../../types';

interface AddBrandModalProps {
  isOpen: boolean;
  onClose: () => void;
  onBrandCreated?: (brand: Brand) => void;
  initialName?: string;
}

export const AddBrandModal: React.FC<AddBrandModalProps> = ({
  isOpen,
  onClose,
  onBrandCreated,
  initialName = '',
}) => {
  const [name, setName] = useState(initialName);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setName(initialName);
      setError(null);
      setIsLoading(false);
    }
  }, [isOpen, initialName]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Please enter a brand name.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const created = await apiClient.createBrand({ name: trimmed });
      if (onBrandCreated) {
        onBrandCreated(created);
      }
      onClose();
    } catch (err: any) {
      const message =
        err?.response?.data?.error?.message ||
        err?.data?.error?.message ||
        err?.message ||
        'Failed to add brand. Please try again.';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-md bg-surface rounded-2xl shadow-2xl border border-surface-container-highest overflow-hidden text-on-surface">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-container-highest bg-surface-container-low">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary-container text-on-primary-container">
              <Tag className="w-5 h-5 text-secondary-container" />
            </div>
            <div>
              <h3 className="text-base font-bold text-on-surface">Add New Brand</h3>
              <p className="text-xs text-on-surface-variant">Register a new product brand in master data</p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="p-1.5 rounded-lg text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-colors disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="flex items-start gap-2.5 p-3 rounded-xl bg-error-container/20 border border-error-container text-error text-xs font-medium animate-in fade-in">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">
              Brand Name <span className="text-error">*</span>
            </label>
            <input
              type="text"
              autoFocus
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (error) setError(null);
              }}
              placeholder="e.g. Panasonic, Philips, Crompton"
              disabled={isLoading}
              className="w-full px-3.5 py-2.5 rounded-xl border border-outline bg-surface text-on-surface text-sm focus:outline-none focus:ring-2 focus:ring-secondary/50 focus:border-secondary transition-all disabled:opacity-60"
            />
            <p className="mt-1.5 text-[11px] text-on-surface-variant">
              Names are checked case-insensitively to prevent duplicates (e.g. &quot;USHA&quot; matches &quot;usha&quot;).
            </p>
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-surface-container-highest">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2 rounded-xl text-xs font-semibold border border-surface-container-highest text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !name.trim()}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-primary text-on-primary hover:bg-primary/90 transition-all shadow-sm disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <>
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Brand</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
