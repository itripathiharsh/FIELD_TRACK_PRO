import React from 'react';
import { FileText } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';

/**
 * Requirement forms.
 *
 * FT-029: this page listed three invented templates ("Site Security Inspection
 * Form v1.4", "Customer Delivery Acknowledgement v2.1", "Equipment Installation
 * Checklist v1.0") with fabricated field counts and non-functional Edit and
 * New Template buttons. None of it came from the system, and an administrator
 * could reasonably believe those templates existed.
 *
 * The `requirement_forms` and `requirement_categories` tables and models exist,
 * but the backend exposes no endpoints for them (07_api_design.md section 6
 * specifies GET/POST /requirement-categories and the per-visit form routes).
 * Implementing that module is new feature work, tracked as FT-066 - see
 * docs/REPAIR_DECISIONS.md RD-004.
 *
 * Until then this page states the truth instead of simulating a feature.
 */
export const FormsPage: React.FC = () => {
  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Requirement Forms & Templates"
        subtitle="Inspection checklists and field form templates for representatives."
      />

      <EmptyState
        icon={FileText}
        title="Requirement forms are not yet available"
        subtitle="Field representatives cannot capture requirement forms in this build. The capability is specified but not implemented."
      />

      <Card variant="flat" className="bg-primary-tint/20 border-primary-fixed-dim">
        <h4 className="font-headline-sm text-sm font-bold text-primary mb-space-2">
          What is missing
        </h4>
        <ul className="font-caption text-xs text-on-surface-variant leading-relaxed list-disc pl-space-4 space-y-1">
          <li>Requirement category management (admin-editable taxonomy).</li>
          <li>Per-visit requirement capture and retrieval.</li>
          <li>Customer and employee signature capture.</li>
        </ul>
        <p className="font-caption text-xs text-on-surface-variant leading-relaxed mt-space-3">
          The database schema for these records already exists; the API endpoints do not. No
          placeholder templates are shown here, because presenting forms that cannot be filled in
          would misrepresent the system&apos;s capability.
        </p>
      </Card>
    </div>
  );
};
