import React, { useCallback, useEffect, useState } from 'react';
import { Plus, FileText, Tag, Trash2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Input } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { apiClient, RequirementCategory } from '../api/client';

/**
 * Requirement forms management.
 *
 * Manages requirement categories and allows viewing/submitting forms.
 */
export const FormsPage: React.FC = () => {
    const [categories, setCategories] = useState<RequirementCategory[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newCategoryName, setNewCategoryName] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);

    const loadCategories = useCallback(async () => {
        try {
            setIsLoading(true);
            const data = await apiClient.getRequirementCategories();
            setCategories(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load categories');
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        loadCategories();
    }, [loadCategories]);

    const handleCreateCategory = async () => {
        if (!newCategoryName.trim()) return;
        try {
            setIsSubmitting(true);
            await apiClient.request('/api/v1/requirement-categories', {
                method: 'POST',
                body: JSON.stringify({ name: newCategoryName.trim() }),
            });
            setNewCategoryName('');
            setShowCreateModal(false);
            loadCategories();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create category');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="space-y-space-6 font-body-md text-on-surface">
            <PageHeader
                title="Requirement Forms & Templates"
                subtitle="Manage requirement categories and capture forms."
                actions={
                    <Button size="sm" icon={Plus} onClick={() => setShowCreateModal(true)}>
                        New Category
                    </Button>
                }
            />

            {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

            {isLoading ? (
                <Card>
                    <div className="flex items-center justify-center h-32">
                        <div className="w-8 h-8 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
                    </div>
                </Card>
            ) : categories.length === 0 ? (
                <EmptyState
                    icon={FileText}
                    title="No Categories"
                    subtitle="Create requirement categories to organize field forms."
                />
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-space-4">
                    {categories.map((cat) => (
                        <Card key={cat.id} modifier="hover">
                            <CardHeader>
                                <div className="flex items-center gap-space-2">
                                    <Tag className="w-4 h-4 text-primary" />
                                    <CardTitle>{cat.name}</CardTitle>
                                </div>
                                <CardSubtitle>
                                    {cat.is_active ? 'Active' : 'Inactive'}
                                </CardSubtitle>
                            </CardHeader>
                        </Card>
                    ))}
                </div>
            )}

            <Modal
                isOpen={showCreateModal}
                onClose={() => setShowCreateModal(false)}
                title="New Requirement Category"
            >
                <div className="space-y-space-4">
                    <Input
                        label="Category Name"
                        value={newCategoryName}
                        onChange={(e) => setNewCategoryName(e.target.value)}
                        placeholder="e.g., Site Inspection"
                    />
                    <div className="flex justify-end gap-space-2">
                        <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleCreateCategory} disabled={isSubmitting || !newCategoryName.trim()}>
                            {isSubmitting ? 'Creating...' : 'Create'}
                        </Button>
                    </div>
                </div>
            </Modal>
        </div>
    );
};
