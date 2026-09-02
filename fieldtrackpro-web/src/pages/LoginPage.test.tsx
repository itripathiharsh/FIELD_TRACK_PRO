import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LoginPage } from './LoginPage';
import { apiClient } from '../api/client';
import { AuthProvider } from '../context/AuthContext';

// Mock apiClient methods
vi.mock('../api/client', () => ({
  apiClient: {
    login: vi.fn(),
    forgotPassword: vi.fn(),
    verifyOtp: vi.fn(),
    resetPassword: vi.fn(),
    getCurrentUser: vi.fn(),
    hasStoredSession: vi.fn(() => false),
    getAccessToken: vi.fn(() => null),
  },
}));

describe('LoginPage and Password Recovery Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderComponent = () =>
    render(
      <MemoryRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>
    );

  it('renders login form by default with email/mobile input and password', () => {
    renderComponent();
    expect(screen.getByLabelText(/work email or mobile/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/enter password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in to command center/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /forgot password\?/i })).toBeInTheDocument();
  });

  it('navigates to Step 1 Forgot Password on click', () => {
    renderComponent();
    fireEvent.click(screen.getByRole('button', { name: /forgot password\?/i }));
    expect(screen.getByRole('heading', { name: /reset password/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send verification code/i })).toBeInTheDocument();
  });

  it('executes full 4-step recovery flow with mobile number', async () => {
    vi.mocked(apiClient.forgotPassword).mockResolvedValueOnce({
      message: 'Security code sent successfully.',
      destination: '******1014',
      delivery_channel: 'SMS',
    });
    vi.mocked(apiClient.verifyOtp).mockResolvedValueOnce({
      valid: true,
      message: 'Verification code confirmed.',
    });
    vi.mocked(apiClient.resetPassword).mockResolvedValueOnce({
      message: 'Password updated successfully',
    });

    renderComponent();

    // 1. Go to forgot password
    fireEvent.click(screen.getByRole('button', { name: /forgot password\?/i }));
    
    // 2. Enter mobile number and submit Step 1
    const mobileInput = screen.getByLabelText(/work email or mobile/i);
    fireEvent.change(mobileInput, { target: { value: '9839011014' } });
    fireEvent.click(screen.getByRole('button', { name: /send verification code/i }));

    // 3. Verify Step 2 shows masked destination
    await waitFor(() => {
      expect(screen.getByText('******1014')).toBeInTheDocument();
      expect(screen.getByText(/sms code sent/i)).toBeInTheDocument();
    });

    // 4. Enter OTP in Step 2
    const otpInput = screen.getByLabelText(/6-digit verification code/i);
    fireEvent.change(otpInput, { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: /verify code/i }));

    // 5. Verify Step 3: New Password form appears
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /new password/i })).toBeInTheDocument();
    });

    // 6. Enter matching new passwords
    const newPassInput = screen.getByLabelText(/^new password/i);
    const confirmPassInput = screen.getByLabelText(/confirm new password/i);
    fireEvent.change(newPassInput, { target: { value: 'NewSecurePass123!' } });
    fireEvent.change(confirmPassInput, { target: { value: 'NewSecurePass123!' } });

    fireEvent.click(screen.getByRole('button', { name: /save new password/i }));

    // 7. Verify Step 4: Success state
    await waitFor(() => {
      expect(screen.getByText(/password updated successfully/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /back to sign in/i })).toBeInTheDocument();
    });

    // 8. Return to login
    fireEvent.click(screen.getByRole('button', { name: /back to sign in/i }));
    expect(screen.getByRole('heading', { name: /command portal/i })).toBeInTheDocument();
  });
});
