import React from 'react';
import { Camera, CameraOff } from 'lucide-react';
import { Customer } from '../../types';

/** Compact "Photo ✓ / No photo" chip + confirmation count for the customers list. */
export const OutletPhotoChip: React.FC<{ customer: Pick<Customer, 'primary_outlet_image_available' | 'outlet_location_confirmations'> }> = ({
  customer,
}) => {
  const has = customer.primary_outlet_image_available === true;
  const n = customer.outlet_location_confirmations ?? 0;
  return (
    <div className="space-y-1 text-xs">
      {has ? (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-100 text-emerald-900 border border-emerald-300">
          <Camera className="w-3 h-3" /> Photo ✓
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-300">
          <CameraOff className="w-3 h-3" /> No photo
        </span>
      )}
      {n > 0 && <p className="text-[10px] text-on-surface-variant">Confirmed by {n}</p>}
    </div>
  );
};
