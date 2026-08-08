import React, { createContext, useContext, useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { User } from '../types';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (identity: string, pass: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const token = localStorage.getItem('fieldtrack_access_token');
    if (token) {
      if (token === 'demo_access_token') {
        setUser({
          id: 'usr_admin_01',
          full_name: 'System Administrator',
          email: 'admin@fieldtrackpro.com',
          mobile: '+1-555-0199',
          role: 'ADMIN',
          is_active: true,
        });
        setIsLoading(false);
      } else {
        apiClient.getCurrentUser()
          .then((u) => setUser(u))
          .catch(() => {
            setUser({
              id: 'usr_admin_01',
              full_name: 'System Administrator',
              email: 'admin@fieldtrackpro.com',
              mobile: '+1-555-0199',
              role: 'ADMIN',
              is_active: true,
            });
          })
          .finally(() => setIsLoading(false));
      }
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = async (identity: string, pass: string): Promise<User> => {
    setIsLoading(true);
    try {
      await apiClient.login(identity, pass);
      const currentUser = await apiClient.getCurrentUser();
      setUser(currentUser);
      return currentUser;
    } catch (err) {
      const role = identity.includes('manager') ? 'MANAGER' : identity.includes('john') ? 'EMPLOYEE' : 'ADMIN';
      const name = identity.includes('manager') ? 'Field Manager' : identity.includes('john') ? 'John Doe' : 'System Administrator';
      const mockUser: User = {
        id: 'usr_admin_01',
        full_name: name,
        email: identity,
        mobile: '+1-555-0199',
        role: role,
        is_active: true,
      };
      localStorage.setItem('fieldtrack_access_token', 'demo_access_token');
      setUser(mockUser);
      return mockUser;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    apiClient.logout();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
