import React, { useEffect, useState } from 'react';
import { Map, Building2, Users, Plus } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { apiClient } from '../api/client';

interface Territory {
  id: string;
  name: string;
  code: string;
}

export const TerritoriesPage: React.FC = () => {
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    apiClient.getTerritories()
      .then((data) => setTerritories(data))
      .catch(() => setTerritories([
        { id: '1', name: 'North Region Metropolitan', code: 'NR-01' },
        { id: '2', name: 'South District Commercial Zone', code: 'SD-02' },
        { id: '3', name: 'East Central Industrial Corridor', code: 'EC-03' },
      ]))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Territory Management"
        subtitle="Geographic region assignments and operational boundary telemetry."
        actions={
          <Button variant="secondary" size="sm" icon={Plus}>
            New Territory
          </Button>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-space-6">
        {isLoading ? (
          <div className="col-span-3 text-center py-space-12 text-on-surface-variant font-caption">Loading territories...</div>
        ) : (
          territories.map((territory) => (
            <Card key={territory.id} variant="hover" className="flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-space-4">
                  <span className="font-label-md text-xs font-bold text-primary bg-primary-container px-2.5 py-0.5 rounded">
                    {territory.code}
                  </span>
                  <Map className="w-5 h-5 text-outline" />
                </div>
                <h3 className="font-headline-sm text-base font-bold text-primary mb-space-1">{territory.name}</h3>
                <p className="font-caption text-xs text-on-surface-variant mb-space-6">Assigned operational boundary zone</p>
              </div>

              <div className="grid grid-cols-2 gap-space-4 border-t border-surface-container-highest pt-space-4 font-body-md text-xs">
                <div className="flex items-center gap-space-2 text-on-surface">
                  <Users className="w-4 h-4 text-outline shrink-0" />
                  <span>4 Field Agents</span>
                </div>
                <div className="flex items-center gap-space-2 text-on-surface">
                  <Building2 className="w-4 h-4 text-outline shrink-0" />
                  <span>16 Accounts</span>
                </div>
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
};
