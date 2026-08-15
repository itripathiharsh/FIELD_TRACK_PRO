import React, { useState } from 'react';
import { Modal } from './Modal';
import { Button } from './Button';
import { Input } from './Input';
import { Select } from './Select';
import { Textarea } from './Textarea';
import { ErrorBanner } from './ErrorBanner';
import { apiClient } from '../../api/client';
import { PaymentMethod, Invoice } from '../../types';

interface CollectPaymentModalProps {
  isOpen: boolean;
  onClose: () => void;
  visitId: string;
  /** Optional - lets the employee tie the collection to a specific outstanding invoice. */
  outstandingInvoices?: Invoice[];
  onCollected: () => void;
}

const todayIso = () => new Date().toISOString().slice(0, 10);

/**
 * Employee-side payment collection: amount + method-specific fields (cheque
 * number/bank, or UTR) + payment date, then an optional proof photo
 * (cheque photo or payment screenshot). Submits as PENDING_VERIFICATION -
 * an accountant/admin must verify it before it counts toward the outlet's
 * paid/outstanding totals.
 */
export const CollectPaymentModal: React.FC<CollectPaymentModalProps> = ({
  isOpen,
  onClose,
  visitId,
  outstandingInvoices = [],
  onCollected,
}) => {
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState<PaymentMethod>('CASH');
  const [paymentDate, setPaymentDate] = useState(todayIso());
  const [invoiceId, setInvoiceId] = useState('');
  const [chequeNumber, setChequeNumber] = useState('');
  const [chequeBankName, setChequeBankName] = useState('');
  const [utrReference, setUtrReference] = useState('');
  const [notes, setNotes] = useState('');
  const [proofFile, setProofFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setAmount('');
    setMethod('CASH');
    setPaymentDate(todayIso());
    setInvoiceId('');
    setChequeNumber('');
    setChequeBankName('');
    setUtrReference('');
    setNotes('');
    setProofFile(null);
    setError(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const parsedAmount = parseFloat(amount);
    if (Number.isNaN(parsedAmount) || parsedAmount <= 0) {
      setError('Enter a valid payment amount.');
      return;
    }
    if (method === 'CHEQUE' && !chequeNumber.trim()) {
      setError('Cheque number is required for cheque payments.');
      return;
    }
    if (method === 'ONLINE' && !utrReference.trim()) {
      setError('UTR reference is required for online payments.');
      return;
    }

    setIsSubmitting(true);
    try {
      const payment = await apiClient.createPayment({
        visit_id: visitId,
        invoice_id: invoiceId || null,
        amount: parsedAmount,
        payment_method: method,
        payment_date: paymentDate,
        cheque_number: method === 'CHEQUE' ? chequeNumber : null,
        cheque_bank_name: method === 'CHEQUE' ? chequeBankName || null : null,
        utr_reference: method === 'ONLINE' ? utrReference : null,
        notes: notes || null,
      });

      if (proofFile) {
        try {
          await apiClient.uploadPaymentProof(payment.id, proofFile);
        } catch (proofErr) {
          // The collection itself is already recorded; surface the proof
          // failure but don't lose the payment - the employee can retry the
          // proof upload later from the account panel.
          setError(
            proofErr instanceof Error
              ? `Payment recorded, but the proof upload failed: ${proofErr.message}`
              : 'Payment recorded, but the proof upload failed.',
          );
          onCollected();
          setIsSubmitting(false);
          return;
        }
      }

      onCollected();
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to record payment');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Collect Payment" subtitle="Record a cash, cheque, or online collection for this visit">
      <form onSubmit={handleSubmit} className="space-y-space-4">
        {error && <ErrorBanner message={error} />}

        <Input
          label="Amount (₹)"
          type="number"
          min="0.01"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          required
        />

        <Select label="Payment Method" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
          <option value="CASH">Cash</option>
          <option value="CHEQUE">Cheque</option>
          <option value="ONLINE">Online / UPI / Bank Transfer</option>
        </Select>

        <Input
          label="Payment Date"
          type="date"
          value={paymentDate}
          onChange={(e) => setPaymentDate(e.target.value)}
          max={todayIso()}
          required
        />

        {outstandingInvoices.length > 0 && (
          <Select
            label="Apply to Invoice (optional)"
            value={invoiceId}
            onChange={(e) => setInvoiceId(e.target.value)}
            helperText="Leave blank if unsure - the accountant can allocate it later."
          >
            <option value="">Not tied to a specific invoice</option>
            {outstandingInvoices.map((inv) => (
              <option key={inv.id} value={inv.id}>
                {inv.invoice_number} - ₹{Number(inv.remaining_amount).toLocaleString('en-IN')} remaining
              </option>
            ))}
          </Select>
        )}

        {method === 'CHEQUE' && (
          <>
            <Input
              label="Cheque Number"
              value={chequeNumber}
              onChange={(e) => setChequeNumber(e.target.value)}
              required
            />
            <Input
              label="Bank Name"
              value={chequeBankName}
              onChange={(e) => setChequeBankName(e.target.value)}
            />
          </>
        )}

        {method === 'ONLINE' && (
          <Input
            label="UTR / Reference Number"
            value={utrReference}
            onChange={(e) => setUtrReference(e.target.value)}
            required
          />
        )}

        <div className="w-full flex flex-col gap-space-1.5">
          <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
            {method === 'CHEQUE' ? 'Cheque Photo' : method === 'ONLINE' ? 'Payment Screenshot' : 'Receipt Photo (optional)'}
          </label>
          <input
            type="file"
            accept="image/*,application/pdf"
            onChange={(e) => setProofFile(e.target.files?.[0] ?? null)}
            className="text-sm text-on-surface-variant"
          />
        </div>

        <Textarea
          label="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
        />

        <div className="flex gap-space-3 pt-space-2">
          <Button type="button" variant="outline" className="flex-1" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" className="flex-1" isLoading={isSubmitting}>
            Record Collection
          </Button>
        </div>
      </form>
    </Modal>
  );
};
