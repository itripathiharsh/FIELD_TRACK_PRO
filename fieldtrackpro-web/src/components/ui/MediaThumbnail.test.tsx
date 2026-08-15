import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { MediaThumbnail } from './MediaThumbnail';
import { MEDIA } from '../../test/utils';

// Mock URL methods
URL.createObjectURL = vi.fn().mockReturnValue('blob:test-url');
URL.revokeObjectURL = vi.fn();

// Mock the API client methods
vi.mock('../../api/client', () => ({
    apiClient: {
        getMediaObjectUrl: vi.fn().mockResolvedValue('blob:test-url'),
        deleteMedia: vi.fn().mockResolvedValue(undefined),
    },
}));

// Import after mock
import { apiClient } from '../../api/client';

describe('MediaThumbnail', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // Reset the mock to return resolved values
        (apiClient.getMediaObjectUrl as ReturnType<typeof vi.fn>).mockResolvedValue('blob:test-url');
        (apiClient.deleteMedia as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    });

    it('renders media file name and size', () => {
        render(
            <MemoryRouter>
                <MediaThumbnail media={MEDIA} />
            </MemoryRouter>,
        );

        expect(screen.getByText(/77777777_site.jpg/i)).toBeInTheDocument();
        expect(screen.getByText(/2.0 KB/i)).toBeInTheDocument();
        expect(screen.getByText(/PHOTO/i)).toBeInTheDocument();
    });

    it('shows download button', () => {
        render(
            <MemoryRouter>
                <MediaThumbnail media={MEDIA} />
            </MemoryRouter>,
        );

        expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument();
    });

    it('shows delete button when canDelete is true', () => {
        render(
            <MemoryRouter>
                <MediaThumbnail media={MEDIA} canDelete onDeleted={vi.fn()} />
            </MemoryRouter>,
        );

        expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
    });

    it('hides delete button when canDelete is false', () => {
        render(
            <MemoryRouter>
                <MediaThumbnail media={MEDIA} />
            </MemoryRouter>,
        );

        expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
    });

    it('calls deleteMedia when delete button is clicked', async () => {
        const onDeleted = vi.fn();

        render(
            <MemoryRouter>
                <MediaThumbnail media={MEDIA} canDelete onDeleted={onDeleted} />
            </MemoryRouter>,
        );

        const deleteButton = screen.getByRole('button', { name: /delete/i });
        deleteButton.click();

        await waitFor(() => {
            expect(apiClient.deleteMedia).toHaveBeenCalledWith(MEDIA.id);
        });

        expect(onDeleted).toHaveBeenCalled();
    });

    it('shows error when delete fails', async () => {
        (apiClient.deleteMedia as ReturnType<typeof vi.fn>).mockReset();
        (apiClient.deleteMedia as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
            new Error('Delete failed'),
        );

        render(
            <MemoryRouter>
                <MediaThumbnail media={MEDIA} canDelete onDeleted={vi.fn()} />
            </MemoryRouter>,
        );

        const deleteButton = screen.getByRole('button', { name: /delete/i });
        deleteButton.click();

        await waitFor(() => {
            expect(screen.getByText(/delete failed/i)).toBeInTheDocument();
        });
    });

    it('shows file icon for documents', () => {
        const documentMedia = { ...MEDIA, media_type: 'DOCUMENT' as const };

        render(
            <MemoryRouter>
                <MediaThumbnail media={documentMedia} />
            </MemoryRouter>,
        );

        expect(screen.getByText(/DOCUMENT/i)).toBeInTheDocument();
    });

    it('calls getMediaObjectUrl for photo preview', () => {
        render(
            <MemoryRouter>
                <MediaThumbnail media={MEDIA} />
            </MemoryRouter>,
        );

        expect(apiClient.getMediaObjectUrl).toHaveBeenCalledWith(MEDIA.id);
    });
});
