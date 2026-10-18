import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
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
    clearSession: vi.fn(),
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
    expect(screen.getByPlaceholderText(/enter your password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in to command center/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /forgot password\?/i })).toBeInTheDocument();
  });

  it('tells the user when an admin-issued temporary password has expired (server message, not a generic failure)', async () => {
    vi.mocked(apiClient.login).mockRejectedValueOnce(
      new Error('Your temporary password has expired. Ask your administrator to reset it again.'),
    );
    renderComponent();
    fireEvent.change(screen.getByLabelText(/work email or mobile/i), { target: { value: 'rep@fieldtrack.test' } });
    fireEvent.change(screen.getByPlaceholderText(/enter your password/i), { target: { value: 'Kq7m-Rv4t-Xw9z' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in to command center/i }));
    await waitFor(() => {
      expect(screen.getByText(/temporary password has expired/i)).toBeInTheDocument();
    });
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

  it('renders the split layout: brand panel, welcome copy, phone mockup and APK card', () => {
    renderComponent();
    expect(screen.getAllByText(/your field team\./i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/always connected\./i).length).toBeGreaterThan(0);
    [
      'GPS based visit verification',
      'Real-time field activity',
      'Digital forms & order capture',
      'Attachments & proof',
      'Complete field visibility',
    ].forEach((t) => expect(screen.getAllByText(t).length).toBeGreaterThan(0));
    expect(screen.getByText(/welcome to/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /command portal/i })).toBeInTheDocument();
    expect(
      screen.getByText(/sign in to manage your operations, teams and field data/i),
    ).toBeInTheDocument();
    const phone = screen.getByAltText(/visit details screen/i);
    expect(phone).toHaveAttribute('src', expect.stringContaining('login-phone-mockup'));
    // responsive structure: phone mockup is desktop-only (hidden below lg)
    expect(phone.closest('picture')?.parentElement).toHaveClass('hidden', 'lg:block');
    expect(phone.closest('picture')?.querySelector('source')).toHaveAttribute('type', 'image/webp');
    expect(screen.getByTestId('apk-card')).toBeInTheDocument();
  });

  it('signs in and redirects employees to /visits', async () => {
    vi.mocked(apiClient.login).mockResolvedValueOnce({} as never);
    vi.mocked(apiClient.getCurrentUser).mockResolvedValueOnce({
      id: 'u1',
      full_name: 'Test Rep',
      email: 'rep@example.com',
      role: 'EMPLOYEE',
      is_active: true,
    } as never);
    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/visits" element={<div>VISITS HOME</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/work email or mobile/i), {
      target: { value: ' rep@example.com ' },
    });
    fireEvent.change(screen.getByPlaceholderText(/enter your password/i), {
      target: { value: 'secret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in to command center/i }));
    expect(await screen.findByText('VISITS HOME')).toBeInTheDocument();
    expect(apiClient.login).toHaveBeenCalledWith('rep@example.com', 'secret123');
  });

  it('shows the server error when login fails and stays on the form', async () => {
    vi.mocked(apiClient.login).mockRejectedValueOnce(new Error('Invalid email or password'));
    renderComponent();
    fireEvent.change(screen.getByLabelText(/work email or mobile/i), { target: { value: 'x@y.com' } });
    fireEvent.change(screen.getByPlaceholderText(/enter your password/i), { target: { value: 'bad' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in to command center/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password');
    expect(screen.getByRole('button', { name: /sign in to command center/i })).toBeEnabled();
  });

  it('shows a deactivated-account message', async () => {
    vi.mocked(apiClient.login).mockRejectedValueOnce(new Error('Account is disabled'));
    renderComponent();
    fireEvent.change(screen.getByLabelText(/work email or mobile/i), { target: { value: 'x@y.com' } });
    fireEvent.change(screen.getByPlaceholderText(/enter your password/i), { target: { value: 'pw' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in to command center/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/has been deactivated/i);
  });

  it('marks credentials required and toggles password visibility', () => {
    renderComponent();
    expect(screen.getByLabelText(/work email or mobile/i)).toBeRequired();
    const pw = screen.getByPlaceholderText(/enter your password/i);
    expect(pw).toBeRequired();
    expect(pw).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByRole('button', { name: /show password/i }));
    expect(pw).toHaveAttribute('type', 'text');
  });

  it('shows the session-expired notice', () => {
    render(
      <MemoryRouter initialEntries={[{ pathname: '/login', state: { reason: 'session_expired' } }]}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(screen.getByRole('status')).toHaveTextContent(/session has expired/i);
  });

  it('requires a destination before sending a reset code', () => {
    renderComponent();
    fireEvent.click(screen.getByRole('button', { name: /forgot password\?/i }));
    const form = screen.getByRole('button', { name: /send verification code/i }).closest('form');
    fireEvent.submit(form as HTMLFormElement);
    expect(screen.getByRole('alert')).toHaveTextContent(/enter your email or mobile/i);
    expect(apiClient.forgotPassword).not.toHaveBeenCalled();
  });
});
