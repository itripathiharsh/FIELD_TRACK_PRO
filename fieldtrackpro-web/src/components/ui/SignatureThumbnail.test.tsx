import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { SignatureThumbnail } from './SignatureThumbnail';
import { apiClient } from '../../api/client';

// Mock the API client methods
vi.mock('../../api/client', () => ({
    apiClient: {
        getSignatureDownloadUrl: vi.fn(),
    },
}));

const mockSignature = {
    id: 'sig-123',
    visit_id: 'visit-456',
    signature_type: 'CUSTOMER' as const,
    capture_method: 'SIGNATURE' as const,
    storage_key: 'signatures/visit-456/customer.png',
    content_type: 'image/png',
    file_size_bytes: 2048,
    created_by: 'user-789',
    signed_at: '2026-08-08T12:00:00Z',
    superseded_at: null,
};

describe('SignatureThumbnail', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders signature type and date', () => {
        render(
            <MemoryRouter>
                <SignatureThumbnail signature={mockSignature} />
            </MemoryRouter>,
        );

        expect(screen.getByText(/customer acknowledgement/i)).toBeInTheDocument();
        expect(screen.getByText(/signed on screen/i)).toBeInTheDocument();
        expect(screen.getByText(/8\/8\/2026/i)).toBeInTheDocument();
    });

    it('shows "Uploaded photo" for a photo-upload acknowledgement', () => {
        const photoSig = { ...mockSignature, capture_method: 'PHOTO_UPLOAD' as const };

        render(
            <MemoryRouter>
                <SignatureThumbnail signature={photoSig} />
            </MemoryRouter>,
        );

        expect(screen.getByText(/uploaded photo/i)).toBeInTheDocument();
    });

    it('shows download button', () => {
        render(
            <MemoryRouter>
                <SignatureThumbnail signature={mockSignature} />
            </MemoryRouter>,
        );

        expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument();
    });

    it('calls getSignatureDownloadUrl when download is clicked', async () => {
        (apiClient.getSignatureDownloadUrl as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
            download_url: 'https://example.com/download/sig.png',
            expires_in_minutes: 15,
        });

        // Mock window.open
        const windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

        render(
            <MemoryRouter>
                <SignatureThumbnail signature={mockSignature} />
            </MemoryRouter>,
        );

        const downloadButton = screen.getByRole('button', { name: /download/i });
        downloadButton.click();

        await waitFor(() => {
            expect(apiClient.getSignatureDownloadUrl).toHaveBeenCalledWith(mockSignature.id);
        });

        expect(windowOpenSpy).toHaveBeenCalledWith('https://example.com/download/sig.png', '_blank');
        windowOpenSpy.mockRestore();
    });

    it('shows error when download fails', async () => {
        (apiClient.getSignatureDownloadUrl as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
            new Error('Download failed'),
        );

        render(
            <MemoryRouter>
                <SignatureThumbnail signature={mockSignature} />
            </MemoryRouter>,
        );

        const downloadButton = screen.getByRole('button', { name: /download/i });
        downloadButton.click();

        await waitFor(() => {
            expect(screen.getByText(/download failed/i)).toBeInTheDocument();
        });
    });

    it('renders employee signature type correctly', () => {
        const employeeSig = { ...mockSignature, signature_type: 'EMPLOYEE' as const };

        render(
            <MemoryRouter>
                <SignatureThumbnail signature={employeeSig} />
            </MemoryRouter>,
        );

        expect(screen.getByText(/employee signature/i)).toBeInTheDocument();
    });
});
