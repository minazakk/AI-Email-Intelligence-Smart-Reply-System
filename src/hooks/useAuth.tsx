'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { UserOut, TokenResponse } from '@/types/api';
import { authApi } from '@/lib/api';

interface AuthContextType {
  user: UserOut | null;
  accessToken: string | null;
  refreshToken: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (data: { email: string; password: string; full_name?: string; timezone?: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshAccessToken: () => Promise<void>;
  updateUser: (data: { full_name?: string; timezone?: string }) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = !!user && !!accessToken;

  const loadTokens = useCallback(async () => {
    if (typeof window === 'undefined') return;
    
    const storedAccess = localStorage.getItem('access_token');
    const storedRefresh = localStorage.getItem('refresh_token');
    
    if (storedAccess && storedRefresh) {
      setAccessToken(storedAccess);
      setRefreshToken(storedRefresh);
      
      try {
        const userData = await authApi.me();
        setUser(userData);
      } catch {
        // Token might be expired, try to refresh
        try {
          await refreshAccessToken();
        } catch {
          // Refresh failed, clear tokens
          clearAuth();
        }
      }
    }
    setIsLoading(false);
  }, []);

  const setAuthCookies = useCallback((access: string, refresh: string) => {
    document.cookie = `access_token=${access}; path=/; max-age=1800; samesite=lax`;
    document.cookie = `refresh_token=${refresh}; path=/; max-age=1209600; samesite=lax`;
  }, []);

  const clearAuth = useCallback(() => {
    setUser(null);
    setAccessToken(null);
    setRefreshToken(null);
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    document.cookie = 'access_token=; path=/; max-age=0';
    document.cookie = 'refresh_token=; path=/; max-age=0';
  }, []);

  const refreshAccessToken = useCallback(async () => {
    const storedRefresh = localStorage.getItem('refresh_token');
    if (!storedRefresh) throw new Error('No refresh token');
    
    const response = await authApi.refresh(storedRefresh);
    setAccessToken(response.access_token);
    setRefreshToken(response.refresh_token);
    setUser(response.user);
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('refresh_token', response.refresh_token);
    setAuthCookies(response.access_token, response.refresh_token);
  }, [setAuthCookies]);

  useEffect(() => {
    loadTokens();
  }, [loadTokens]);

  const login = async (email: string, password: string) => {
    const response = await authApi.login({ email, password });
    setAccessToken(response.access_token);
    setRefreshToken(response.refresh_token);
    setUser(response.user);
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('refresh_token', response.refresh_token);
    setAuthCookies(response.access_token, response.refresh_token);
  };

  const signup = async (data: { email: string; password: string; full_name?: string; timezone?: string }) => {
    const response = await authApi.signup(data);
    setAccessToken(response.access_token);
    setRefreshToken(response.refresh_token);
    setUser(response.user);
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('refresh_token', response.refresh_token);
    setAuthCookies(response.access_token, response.refresh_token);
  };

  const logout = async () => {
    const storedRefresh = localStorage.getItem('refresh_token');
    if (storedRefresh) {
      try {
        await authApi.logout(storedRefresh);
      } catch {
        // Ignore logout errors
      }
    }
    clearAuth();
  };

  const updateUser = async (data: { full_name?: string; timezone?: string }) => {
    const updatedUser = await authApi.updateMe(data);
    setUser(updatedUser);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        refreshToken,
        isLoading,
        isAuthenticated,
        login,
        signup,
        logout,
        refreshAccessToken,
        updateUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}