import React, { useState, useEffect, useMemo } from 'react';
import { Tag, Plus, X, Check, ChevronsUpDown } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Brand } from '../../types';
import { AddBrandModal } from './AddBrandModal';

interface BrandSelectProps {
  label?: string;
  selectedBrands: string[];
  onChange: (brands: string[]) => void;
  error?: string;
  helperText?: string;
  placeholder?: string;
  disabled?: boolean;
}

export const BrandSelect: React.FC<BrandSelectProps> = ({
  label = 'Associated Brands',
  selectedBrands = [],
  onChange,
  error,
  helperText,
  placeholder = 'Select brands...',
  disabled = false,
}) => {
  const [brands, setBrands] = useState<Brand[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [search, setSearch] = useState('');

  const loadBrands = async () => {
    try {
      setIsLoading(true);
      const list = await apiClient.getBrands(true);
      setBrands(list);
    } catch {
      // Fallback if needed
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadBrands();
  }, []);

  const filteredBrands = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return brands;
    return brands.filter(
      (b) =>
        b.name.toLowerCase().includes(q) ||
        b.normalized_name.toLowerCase().includes(q)
    );
  }, [brands, search]);

  const toggleBrand = (brandName: string) => {
    if (selectedBrands.includes(brandName)) {
      onChange(selectedBrands.filter((b) => b !== brandName));
    } else {
      onChange([...selectedBrands, brandName]);
    }
  };

  const removeBrand = (brandName: string) => {
    onChange(selectedBrands.filter((b) => b !== brandName));
  };

  const handleBrandCreated = (newBrand: Brand) => {
    setBrands((prev) => {
      if (prev.some((b) => b.id === newBrand.id || b.normalized_name === newBrand.normalized_name)) {
        return prev;
      }
      return [...prev, newBrand].sort((a, b) => a.name.localeCompare(b.name));
    });
    if (!selectedBrands.includes(newBrand.name)) {
      onChange([...selectedBrands, newBrand.name]);
    }
  };

  return (
    <div className="space-y-1.5 font-body-md text-xs">
      {label && (
        <label className="block text-xs font-bold uppercase tracking-wider text-on-surface-variant">
          {label}
        </label>
      )}

      {/* Selected Brand Chips */}
      <div className="flex flex-wrap gap-1.5 min-h-[32px] p-2 rounded-xl border border-outline bg-surface focus-within:border-secondary transition-all">
        {selectedBrands.map((b) => (
          <span
            key={b}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-primary-container/20 border border-primary-container/40 text-primary text-xs font-semibold animate-in fade-in zoom-in-95"
          >
            <Tag className="w-3 h-3 text-secondary" />
            <span>{b}</span>
            {!disabled && (
              <button
                type="button"
                onClick={() => removeBrand(b)}
                className="p-0.5 rounded-full hover:bg-primary-container/30 text-on-surface-variant hover:text-on-surface transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </span>
        ))}

        {!disabled && (
          <div className="relative flex-1 min-w-[140px] flex items-center">
            <button
              type="button"
              onClick={() => setIsDropdownOpen((prev) => !prev)}
              className="flex items-center justify-between w-full text-left py-0.5 px-1 text-xs text-on-surface-variant hover:text-on-surface focus:outline-none"
            >
              <span>{selectedBrands.length === 0 ? placeholder : 'Add more...'}</span>
              <ChevronsUpDown className="w-3.5 h-3.5 opacity-50" />
            </button>

            {/* Dropdown Menu */}
            {isDropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-20"
                  onClick={() => setIsDropdownOpen(false)}
                />
                <div className="absolute top-full left-0 right-0 mt-2 z-30 bg-surface rounded-xl shadow-xl border border-surface-container-highest max-h-60 overflow-y-auto p-1.5 space-y-1 animate-in fade-in zoom-in-95">
                  <div className="p-1 border-b border-surface-container-highest">
                    <input
                      type="text"
                      placeholder="Search brands..."
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-lg border border-outline bg-surface-container-low text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-secondary"
                      onClick={(e) => e.stopPropagation()}
                    />
                  </div>

                  <div className="py-1">
                    {filteredBrands.map((brand) => {
                      const isSelected = selectedBrands.includes(brand.name);
                      return (
                        <button
                          key={brand.id}
                          type="button"
                          onClick={() => toggleBrand(brand.name)}
                          className={`flex items-center justify-between w-full px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                            isSelected
                              ? 'bg-primary/10 text-primary font-bold'
                              : 'text-on-surface hover:bg-surface-container'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <Tag className={`w-3.5 h-3.5 ${isSelected ? 'text-primary' : 'text-on-surface-variant'}`} />
                            <span>{brand.name}</span>
                          </div>
                          {isSelected && <Check className="w-3.5 h-3.5 text-primary" />}
                        </button>
                      );
                    })}

                    {filteredBrands.length === 0 && !isLoading && (
                      <div className="px-3 py-2 text-xs text-on-surface-variant italic text-center">
                        No brands found
                      </div>
                    )}
                  </div>

                  {/* Add New Brand Action */}
                  <div className="pt-1 border-t border-surface-container-highest">
                    <button
                      type="button"
                      onClick={() => {
                        setIsDropdownOpen(false);
                        setIsAddModalOpen(true);
                      }}
                      className="flex items-center gap-2 w-full px-2.5 py-2 rounded-lg text-xs font-bold text-secondary hover:bg-secondary/10 transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                      <span>+ Add New Brand</span>
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {error && <p className="text-[11px] font-medium text-error">{error}</p>}
      {helperText && !error && (
        <p className="text-[11px] text-on-surface-variant">{helperText}</p>
      )}

      {/* Add Brand Modal */}
      <AddBrandModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onBrandCreated={handleBrandCreated}
        initialName={search}
      />
    </div>
  );
};
