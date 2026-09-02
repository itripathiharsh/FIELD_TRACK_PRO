import React, { useState, useMemo, useEffect } from 'react';
import { Plus } from 'lucide-react';
import { Modal } from './Modal';
import { Button } from './Button';
import { Input } from './Input';
import { Select } from './Select';
import { Textarea } from './Textarea';
import { ErrorBanner } from './ErrorBanner';
import { AddBrandModal } from './AddBrandModal';
import { apiClient } from '../../api/client';
import { PaymentMethod, Invoice, BrandSummary, Brand } from '../../types';

interface CollectPaymentModalProps {
  isOpen: boolean;
  onClose: () => void;
  visitId: string;
  invoices?: Invoice[];
  outstandingInvoices?: Invoice[];
  brandSummaries?: BrandSummary[];
  onPaymentCollected?: () => void;
  onCollected?: () => void;
}

function todayIso(): string {
  return new Date().toISOString().split('T')[0];
}

const formatCurrency = (value: string | number): string => {
  const num = typeof value === 'string' ? parseFloat(value) || 0 : value;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(num);
};

/**
 * Employee-side payment collection with strict Brand-Wise Allocation support.
 * Renders dynamic brand rows loaded from master catalog with automatic total calculation.
 */
export const CollectPaymentModal: React.FC<CollectPaymentModalProps> = ({
  isOpen,
  onClose,
  visitId,
  invoices = [],
  outstandingInvoices = [],
  brandSummaries = [],
  onPaymentCollected,
  onCollected,
}) => {
  const [brandAmounts, setBrandAmounts] = useState<Record<string, string>>({});
  const [method, setMethod] = useState<PaymentMethod>('CASH');
  const [paymentDate, setPaymentDate] = useState(todayIso());
  const [chequeNumber, setChequeNumber] = useState('');
  const [chequeBankName, setChequeBankName] = useState('');
  const [utrReference, setUtrReference] = useState('');
  const [notes, setNotes] = useState('');
  const [proofFile, setProofFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [brandsLoading, setBrandsLoading] = useState(false);

  const [extraBrands, setExtraBrands] = useState<{ brand: string; outstanding: string }[]>([]);
  const [isAddBrandOpen, setIsAddBrandOpen] = useState(false);
  const [masterBrands, setMasterBrands] = useState<Brand[]>([]);

  useEffect(() => {
    if (isOpen) {
      setBrandsLoading(true);
      apiClient
        .getBrands(true)
        .then((b) => {
          setMasterBrands(b || []);
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : 'Failed to load brand catalog');
        })
        .finally(() => {
          setBrandsLoading(false);
        });
    }
  }, [isOpen]);

  const activeOutstandingInvoices = useMemo(() => {
    if (outstandingInvoices.length > 0) return outstandingInvoices;
    return invoices.filter((i) => parseFloat(i.remaining_amount) > 0);
  }, [invoices, outstandingInvoices]);

  // Extract distinct brand list from summaries, invoices, or master brands
  const availableBrands = useMemo(() => {
    const list: { brand: string; outstanding: string }[] = [];
    const seen = new Set<string>();

    for (const bs of brandSummaries) {
      if (bs.brand && !seen.has(bs.brand.toLowerCase())) {
        seen.add(bs.brand.toLowerCase());
        list.push({ brand: bs.brand, outstanding: bs.total_outstanding });
      }
    }

    for (const inv of activeOutstandingInvoices) {
      const b = inv.brand || 'General';
      if (!seen.has(b.toLowerCase())) {
        seen.add(b.toLowerCase());
        list.push({ brand: b, outstanding: inv.remaining_amount });
      }
    }

    // If still no brands, populate from dynamically loaded master brands
    if (list.length === 0) {
      for (const m of masterBrands) {
        if (m.name && !seen.has(m.name.toLowerCase())) {
          seen.add(m.name.toLowerCase());
          list.push({ brand: m.name, outstanding: '0.00' });
        }
      }
    }

    return list;
  }, [brandSummaries, activeOutstandingInvoices, masterBrands]);

  const allBrands = useMemo(() => {
    const list = [...availableBrands];
    const seen = new Set(list.map((b) => b.brand.toLowerCase()));
    for (const eb of extraBrands) {
      if (!seen.has(eb.brand.toLowerCase())) {
        seen.add(eb.brand.toLowerCase());
        list.push(eb);
      }
    }
    return list;
  }, [availableBrands, extraBrands]);

  // Compute total amount strictly from brand breakdown
  const computedTotal = useMemo(() => {
    let sum = 0;
    for (const b of allBrands) {
      const val = parseFloat(brandAmounts[b.brand] || '0');
      if (!isNaN(val) && val > 0) sum += val;
    }
    return sum;
  }, [allBrands, brandAmounts]);

  const handleClose = () => {
    setBrandAmounts({});
    setMethod('CASH');
    setPaymentDate(todayIso());
    setChequeNumber('');
    setChequeBankName('');
    setUtrReference('');
    setNotes('');
    setProofFile(null);
    setError(null);
    setExtraBrands([]);
    onClose();
  };

  const handleBrandAmountChange = (brand: string, value: string) => {
    setBrandAmounts((prev) => ({
      ...prev,
      [brand]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (computedTotal <= 0) {
      setError('Please allocate payment against at least one brand.');
      return;
    }

    if (method === 'CHEQUE' && !chequeNumber.trim()) {
      setError('Cheque number is required for Cheque payments.');
      return;
    }

    if (method === 'ONLINE' && !utrReference.trim()) {
      setError('UTR Reference / Transaction ID is required for Online payments.');
      return;
    }

    setIsSubmitting(true);
    try {
      const allocations = allBrands
        .map((b) => {
          const amt = parseFloat(brandAmounts[b.brand] || '0');
          return amt > 0 ? { brand: b.brand, amount: amt } : null;
        })
        .filter((a): a is { brand: string; amount: number } => a !== null);

      if (allocations.length === 0) {
        setError('Please allocate an amount for at least one brand.');
        setIsSubmitting(false);
        return;
      }

      const payment = await apiClient.createPayment({
        visit_id: visitId,
        amount: computedTotal,
        payment_method: method,
        payment_date: paymentDate,
        cheque_number: method === 'CHEQUE' ? chequeNumber : undefined,
        cheque_bank_name: method === 'CHEQUE' ? chequeBankName || undefined : undefined,
        utr_reference: method === 'ONLINE' ? utrReference : undefined,
        notes: notes || undefined,
        allocations,
      });

      if (proofFile) {
        try {
          await apiClient.uploadPaymentProof(payment.id, proofFile);
        } catch {
          // Proof upload error is non-fatal to the payment collection itself
        }
      }

      handleClose();
      if (onPaymentCollected) onPaymentCollected();
      if (onCollected) onCollected();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to record payment.';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBrandCreated = (newBrand: Brand) => {
    setMasterBrands((prev) => {
      if (prev.some((b) => b.id === newBrand.id || b.normalized_name === newBrand.normalized_name)) return prev;
      return [...prev, newBrand];
    });
    setExtraBrands((prev) => {
      if (prev.some((b) => b.brand.toLowerCase() === newBrand.name.toLowerCase())) return prev;
      return [...prev, { brand: newBrand.name, outstanding: '0' }];
    });
  };

  const handleSelectAdditionalBrand = (brandName: string) => {
    if (!brandName) return;
    if (brandName === '__ADD_NEW_BRAND__') {
      setIsAddBrandOpen(true);
      return;
    }
    setExtraBrands((prev) => {
      if (prev.some((b) => b.brand.toLowerCase() === brandName.toLowerCase())) return prev;
      return [...prev, { brand: brandName, outstanding: '0' }];
    });
  };

  const unallocatedMasterBrands = useMemo(() => {
    const allocated = new Set(allBrands.map((b) => b.brand.toLowerCase()));
    return masterBrands.filter((mb) => !allocated.has(mb.name.toLowerCase()));
  }, [allBrands, masterBrands]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Collect Payment"
      subtitle="Record brand-wise payment collection for this visit"
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-space-4">
        {error && <ErrorBanner message={error} />}

        {/* Brand-Wise Allocation Section */}
        <div className="space-y-space-3 bg-surface-container-low p-space-4 rounded-xl border border-outline-variant">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-primary">
              Brand-Wise Outstanding & Collection
            </span>
            <span className="text-xs text-on-surface-variant font-medium">
              Enter amount for one or more brands
            </span>
          </div>

          <div className="space-y-space-2 divide-y divide-outline-variant/40">
            {allBrands.map((b) => (
              <div key={b.brand} className="pt-space-2 first:pt-0 grid grid-cols-1 sm:grid-cols-2 gap-space-2 items-center">
                <div>
                  <p className="font-semibold text-sm text-on-surface">{b.brand}</p>
                  <p className="text-xs text-on-surface-variant">
                    Outstanding: <span className="font-mono font-medium text-on-surface">{formatCurrency(b.outstanding)}</span>
                  </p>
                </div>
                <div>
                  <Input
                    type="number"
                    placeholder="₹ 0.00"
                    min="0"
                    step="0.01"
                    value={brandAmounts[b.brand] || ''}
                    onChange={(e) => handleBrandAmountChange(b.brand, e.target.value)}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Allocate Additional Brand Row */}
          <div className="pt-space-2 border-t border-outline-variant/60 flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <Select
                value=""
                onChange={(e) => handleSelectAdditionalBrand(e.target.value)}
                className="text-xs"
              >
                <option value="">{brandsLoading ? 'Loading brands...' : '+ Allocate another brand...'}</option>
                {unallocatedMasterBrands.map((mb) => (
                  <option key={mb.id} value={mb.name}>{mb.name}</option>
                ))}
                <option value="__ADD_NEW_BRAND__" className="font-bold text-secondary">
                  + Add New Brand
                </option>
              </Select>
            </div>

            <button
              type="button"
              onClick={() => setIsAddBrandOpen(true)}
              className="flex items-center gap-1 text-xs font-bold text-secondary hover:underline"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add New Brand</span>
            </button>
          </div>

          {/* Total Display */}
          <div className="flex items-center justify-between pt-space-3 border-t border-outline-variant">
            <span className="font-bold text-sm text-on-surface">Total Payment Amount:</span>
            <span className="font-mono font-bold text-lg text-primary">
              {formatCurrency(computedTotal)}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-3">
          <Select label="Payment Method" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
            <option value="CASH">Cash</option>
            <option value="CHEQUE">Cheque</option>
            <option value="ONLINE">Online (UPI / NEFT / RTGS)</option>
          </Select>

          <Input
            label="Payment Date"
            type="date"
            value={paymentDate}
            onChange={(e) => setPaymentDate(e.target.value)}
            required
          />
        </div>

        {method === 'CHEQUE' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-3">
            <Input
              label="Cheque Number"
              value={chequeNumber}
              onChange={(e) => setChequeNumber(e.target.value)}
              placeholder="e.g. 123456"
              required
            />
            <Input
              label="Bank Name"
              value={chequeBankName}
              onChange={(e) => setChequeBankName(e.target.value)}
              placeholder="e.g. HDFC Bank"
            />
          </div>
        )}

        {method === 'ONLINE' && (
          <Input
            label="UTR / Transaction Reference"
            value={utrReference}
            onChange={(e) => setUtrReference(e.target.value)}
            placeholder="e.g. 423984928349"
            required
          />
        )}

        <Textarea
          label="Notes (Optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Any collection notes or remarks"
          rows={2}
        />

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-on-surface-variant mb-space-1">
            Proof of Payment (Cheque photo / Screenshot)
          </label>
          <input
            type="file"
            accept="image/*,.pdf"
            onChange={(e) => setProofFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-on-surface file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-primary file:text-on-primary hover:file:opacity-90 cursor-pointer"
          />
        </div>

        <div className="flex justify-end gap-space-3 pt-space-2">
          <Button type="button" variant="outline" onClick={handleClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" isLoading={isSubmitting} disabled={computedTotal <= 0}>
            Submit Payment ({formatCurrency(computedTotal)})
          </Button>
        </div>
      </form>

      {/* Add Brand Modal */}
      <AddBrandModal
        isOpen={isAddBrandOpen}
        onClose={() => setIsAddBrandOpen(false)}
        onBrandCreated={handleBrandCreated}
      />
    </Modal>
  );
};
