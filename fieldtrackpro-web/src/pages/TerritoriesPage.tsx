import React, { useCallback, useEffect, useState } from 'react';
import { Map, Building2, Users, Plus } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { apiClient } from '../api/client';
import { Customer, Employee, Territory } from '../types';

export const TerritoriesPage: React.FC = () => {
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [name, setName] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  /**
   * FT-017: counts are derived from real data. The page previously printed a
   * hardcoded "4 Field Agents / 16 Accounts" on every card and rendered an
   * undefined `code` badge, because neither exists in the API contract.
   */
  const load = useCallback(() => {
    setIsLoading(true);
    Promise.all([
      apiClient.getTerritories(),
      apiClient.getEmployees().catch(() => [] as Employee[]),
      apiClient.getCustomers().catch(() => [] as Customer[]),
    ])
      .then(([t, e, c]) => {
        setTerritories(t);
        setEmployees(e);
        setCustomers(c);
        setError(null);
      })
      .catch((err: Error) => {
        setTerritories([]);
        setError(err.message || 'Unable to load territories');
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /** FT-018: the "New Territory" button previously had no handler at all. */
  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setIsSaving(true);
    try {
      await apiClient.createTerritory(name.trim());
      setIsModalOpen(false);
      setName('');
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to create territory');
    } finally {
      setIsSaving(false);
    }
  };

  const countEmployees = (territoryId: string) =>
    employees.filter((e) => e.territory_id === territoryId).length;
  const countCustomers = (territoryId: string) =>
    customers.filter((c) => c.territory_id === territoryId).length;

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Territory Management"
        subtitle="Geographic region assignments and operational boundary telemetry."
        actions={
          <Button variant="secondary" size="sm" icon={Plus} onClick={() => setIsModalOpen(true)}>
            New Territory
          </Button>
        }
      />

      {error && <ErrorBanner message={error} onRetry={load} onDismiss={() => setError(null)} />}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} variant="flat" className="animate-pulse">
              <div className="h-4 bg-surface-container-high rounded w-1/3 mb-space-4" />
              <div className="h-5 bg-surface-container-high rounded w-2/3 mb-space-2" />
              <div className="h-3 bg-surface-container-high rounded w-1/2" />
            </Card>
          ))}
        </div>
      ) : territories.length === 0 && !error ? (
        <EmptyState
          icon={Map}
          title="No territories yet"
          subtitle="Create your first territory to group employees and customer sites."
          action={
            <Button variant="secondary" size="sm" icon={Plus} onClick={() => setIsModalOpen(true)}>
              New Territory
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-6">
          {territories.map((territory) => (
            <Card key={territory.id} variant="hover" className="flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-space-4">
                  <span className="font-label-md text-xs font-bold text-primary bg-primary-container px-2.5 py-0.5 rounded">
                    {new Date(territory.created_at).toLocaleDateString()}
                  </span>
                  <Map className="w-5 h-5 text-outline" />
                </div>
                <h3 className="font-headline-sm text-base font-bold text-primary mb-space-1">
                  {territory.name}
                </h3>
                <p className="font-caption text-xs text-on-surface-variant mb-space-6">
                  Assigned operational boundary zone
                </p>
              </div>

              <div className="grid grid-cols-2 gap-space-4 border-t border-surface-container-highest pt-space-4 font-body-md text-xs">
                <div className="flex items-center gap-space-2 text-on-surface">
                  <Users className="w-4 h-4 text-outline shrink-0" />
                  <span>
                    {countEmployees(territory.id)} Field Agent
                    {countEmployees(territory.id) === 1 ? '' : 's'}
                  </span>
                </div>
                <div className="flex items-center gap-space-2 text-on-surface">
                  <Building2 className="w-4 h-4 text-outline shrink-0" />
                  <span>
                    {countCustomers(territory.id)} Account
                    {countCustomers(territory.id) === 1 ? '' : 's'}
                  </span>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Create Territory"
        subtitle="Define a new operational boundary zone."
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-lg border border-error">
            {formError}
          </div>
        )}
        <form onSubmit={handleCreate} className="space-y-space-4">
          <Input
            label="Territory Name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="North Region Metropolitan"
          />
          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button type="button" variant="ghost" size="sm" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="secondary" size="sm" isLoading={isSaving}>
              Save Territory
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
