'use client';

import { ReactNode, useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { 
  LayoutDashboard, 
  Mail, 
  MessageSquare, 
  Bot, 
  Bell, 
  Settings, 
  LogOut,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Archive,
  Star,
  Trash2,
  Send,
  Upload
} from 'lucide-react';

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Inbox', href: '/dashboard/emails', icon: Inbox },
  { name: 'Starred', href: '/dashboard/emails?starred=true', icon: Star },
  { name: 'Archived', href: '/dashboard/emails?archived=true', icon: Archive },
  { name: 'Trash', href: '/dashboard/emails?deleted=true', icon: Trash2 },
  { name: 'Smart Replies', href: '/dashboard/replies', icon: MessageSquare },
  { name: 'AI Assistant', href: '/dashboard/assistant', icon: Bot },
  { name: 'Notifications', href: '/dashboard/notifications', icon: Bell },
  { name: 'Settings', href: '/dashboard/settings', icon: Settings },
];

const actionLinks = [
  { name: 'Compose', href: '/dashboard/emails/compose', icon: Send },
  { name: 'Import', href: '/dashboard/emails/import', icon: Upload },
];

export function DashboardLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isLoading, isAuthenticated } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full"></div>
      </div>
    );
  }

  const handleLogout = async () => {
    await logout();
    router.replace('/login');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Mobile sidebar overlay */}
      {mobileMenuOpen && (
        <div 
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}
      
      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 z-50 h-screen bg-white border-r border-gray-200 transition-all duration-200 lg:translate-x-0 ${
          sidebarOpen ? 'w-64' : 'w-20'
        } ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
        aria-label="Sidebar navigation"
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200">
            <Link href="/dashboard" className="flex items-center gap-2">
              <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
                <Mail className="w-5 h-5 text-white" />
              </div>
              {sidebarOpen && (
                <span className="text-xl font-bold text-gray-900">AI Email</span>
              )}
            </Link>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-1.5 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 lg:hidden"
              aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
            >
              {sidebarOpen ? <ChevronLeft className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
            </button>
          </div>
          
          {/* Navigation */}
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto" aria-label="Main navigation">
            {navigation.map((item) => {
              const isActive = pathname === item.href || 
                (item.href !== '/dashboard/emails' && pathname.startsWith(item.href));
              const hasQueryMatch = item.href.includes('?') && 
                pathname.includes(item.href.split('?')[0]) &&
                pathname.includes(item.href.split('?')[1]);
              
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive || hasQueryMatch
                      ? 'bg-primary-50 text-primary-700'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  } ${!sidebarOpen && 'justify-center'}`}
                  title={sidebarOpen ? undefined : item.name}
                >
                  <item.icon className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
                  {sidebarOpen && <span>{item.name}</span>}
                </Link>
              );
            })}
            
            <div className="pt-4 pb-2">
              {sidebarOpen && <p className="px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Actions</p>}
            </div>
            {actionLinks.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-primary-50 text-primary-700'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  } ${!sidebarOpen && 'justify-center'}`}
                  title={sidebarOpen ? undefined : item.name}
                >
                  <item.icon className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
                  {sidebarOpen && <span>{item.name}</span>}
                </Link>
              );
            })}
          </nav>
          
          {/* User & Logout */}
          <div className="p-3 border-t border-gray-200">
            <div className="flex items-center gap-3 px-3 py-2">
              <div className="w-8 h-8 bg-primary-100 rounded-full flex items-center justify-center flex-shrink-0">
                <span className="text-sm font-medium text-primary-700">
                  {user?.full_name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || 'U'}
                </span>
              </div>
              {sidebarOpen && (
                <div className="flex-1 min-w-0 overflow-hidden">
                  <p className="text-sm font-medium text-gray-900 truncate">{user?.full_name || 'User'}</p>
                  <p className="text-xs text-gray-500 truncate">{user?.email}</p>
                </div>
              )}
            </div>
            <button
              onClick={handleLogout}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900 transition-colors ${
                !sidebarOpen && 'justify-center'
              }`}
              title={sidebarOpen ? undefined : 'Sign out'}
            >
              <LogOut className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
              {sidebarOpen && <span>Sign out</span>}
            </button>
          </div>
        </div>
      </aside>
      
      {/* Main content */}
      <div className={`lg:pl-64 transition-all duration-200 ${sidebarOpen ? 'lg:pl-64' : 'lg:pl-20'}`}>
        {/* Top bar */}
        <header className="sticky top-0 z-30 bg-white border-b border-gray-200">
          <div className="flex items-center justify-between h-16 px-4 sm:px-6">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100"
              aria-label="Open menu"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="flex-1 lg:flex-none" />
            <div className="flex items-center gap-4">
              {/* Search could go here */}
              <div className="hidden sm:block w-64">
                <div className="relative">
                  <input
                    type="search"
                    placeholder="Search emails..."
                    className="w-full pl-10 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-gray-50"
                    aria-label="Search emails"
                  />
                  <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
              </div>
            </div>
          </div>
        </header>
        
        {/* Page content */}
        <main className="p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}