import React from 'react';
import { FileText, Plus, Edit2 } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';

export const FormsPage: React.FC = () => {
  const formTemplates = [
    { id: '1', title: 'Site Security Inspection Form', category: 'Security Audit', version: 'v1.4', questions: 12 },
    { id: '2', title: 'Customer Delivery Acknowledgement', category: 'Logistics', version: 'v2.1', questions: 8 },
    { id: '3', title: 'Equipment Installation Checklist', category: 'Technical Service', version: 'v1.0', questions: 16 },
  ];

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Requirement Forms & Templates"
        subtitle="Inspection checklists and field form templates for representatives."
        actions={
          <Button variant="secondary" size="sm" icon={Plus}>
            New Template
          </Button>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-space-6">
        {formTemplates.map((template) => (
          <Card key={template.id} variant="hover" className="flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-space-4">
                <span className="font-label-md text-xs font-bold text-primary bg-primary-container px-2.5 py-0.5 rounded">
                  {template.version}
                </span>
                <FileText className="w-5 h-5 text-outline" />
              </div>
              <h3 className="font-headline-sm text-base font-bold text-primary mb-space-1">{template.title}</h3>
              <p className="font-caption text-xs text-on-surface-variant mb-space-6">Category: {template.category}</p>
            </div>

            <div className="flex items-center justify-between border-t border-surface-container-highest pt-space-4 font-body-md text-xs">
              <span className="text-on-surface font-semibold">{template.questions} Form Fields</span>
              <Button variant="ghost" size="sm" icon={Edit2}>
                Edit
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
};
