'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useSearchParams, useRouter } from 'next/navigation';
import { emailApi } from '@/lib/api';
import { EmailListItem, EmailFilterParams, Page } from '@/types/api';
import { Search, Star, Archive, Trash2, RefreshCw, Filter, ChevronLeft, ChevronRight, Paperclip, AlertTriangle, Inbox } from 'lucide-react';

const CATEGORIES = ['invoice', 'order', 'support', 'spam', 'newsletter', 'marketing', 'meeting', 'hr', 'finance', 'legal', 'other'];
const PRIORITIES = ['low', 'normal', 'high', 'critical'];

export default function EmailsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [data, setData] = useState<Page<EmailListItem> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState(searchParams.get('q') || '');
  const [selectedCategory, setSelectedCategory] = useState<string>(searchParams.get('category') || '');
  const [selectedPriority, setSelectedPriority] = useState<string>(searchParams.get('priority') || '');
  const [showFilters, setShowFilters] = useState(false);

  const page = parseInt(searchParams.get('page') || '1');
  const starred = searchParams.get('starred') === 'true';
  const archived = searchParams.get('archived') === 'true';
  const deleted = searchParams.get('deleted') === 'true';
  const unread = searchParams.get('unread') === 'true';
  const urgent = searchParams.get('urgent') === 'true';
  const replyRequired = searchParams.get('reply_required') === 'true';
  const actionRequired = searchParams.get('action_required') === 'true';

  const fetchEmails = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      const params: EmailFilterParams = {
        page,
        page_size: 20,
        q: search || undefined,
        category: selectedCategory ? [selectedCategory] : undefined,
        priority: selectedPriority ? [selectedPriority] : undefined,
        starred: starred || undefined,
        archived: archived || undefined,
        deleted: deleted || undefined,
        unread: unread || undefined,
        urgent: urgent || undefined,
        reply_required: replyRequired || undefined,
        action_required: actionRequired || undefined,
        sort_by: 'received_at',
        sort_order: 'desc',
      };
      const result = await emailApi.list(params);
      setData(result);
    } catch (err) {
      setError('Failed to load emails');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [page, search, selectedCategory, selectedPriority, starred, archived, deleted, unread, urgent, replyRequired, actionRequired]);

  useEffect(() => {
    fetchEmails();
  }, [fetchEmails]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const params = new URLSearchParams(searchParams.toString());
    if (search) params.set('q', search);
    else params.delete('q');
    params.set('page', '1');
    router.push(`/dashboard/emails?${params.toString()}`);
  };

  const updateFilter = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    params.set('page', '1');
    router.push(`/dashboard/emails?${params.toString()}`);
  };

  const goToPage = (newPage: number) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('page', String(newPage));
    router.push(`/dashboard/emails?${params.toString()}`);
  };

  const getPriorityColor = (priority: string | null) => {
    switch (priority) {
      case 'critical': return 'bg-red-100 text-red-700';
      case 'high': return 'bg-orange-100 text-orange-700';
      case 'normal': return 'bg-blue-100 text-blue-700';
      case 'low': return 'bg-gray-100 text-gray-700';
      default: return 'bg-gray-100 text-gray-600';
    }
  };

  const getCategoryColor = (category: string | null) => {
    const colors: Record<string, string> = {
      invoice: 'bg-green-100 text-green-700',
      order: 'bg-blue-100 text-blue-700',
      support: 'bg-purple-100 text-purple-700',
      spam: 'bg-red-100 text-red-700',
      newsletter: 'bg-yellow-100 text-yellow-700',
      marketing: 'bg-pink-100 text-pink-700',
      meeting: 'bg-indigo-100 text-indigo-700',
      hr: 'bg-teal-100 text-teal-700',
      finance: 'bg-emerald-100 text-emerald-700',
      legal: 'bg-slate-100 text-slate-700',
      other: 'bg-gray-100 text-gray-700',
    };
    return colors[category || 'other'] || 'bg-gray-100 text-gray-700';
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {starred ? 'Starred' : archived ? 'Archived' : deleted ? 'Trash' : 'Inbox'}
          </h1>
          <p className="text-gray-500 mt-1">{data?.total || 0} emails</p>
        </div>
        <button
          onClick={fetchEmails}
          className="p-2 rounded-lg text-gray-500 hover:bg-gray-100"
          aria-label="Refresh"
        >
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      {/* Search & Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search emails..."
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700"
          >
            Search
          </button>
          <button
            type="button"
            onClick={() => setShowFilters(!showFilters)}
            className={`p-2 rounded-lg border ${showFilters ? 'bg-primary-50 border-primary-300 text-primary-700' : 'border-gray-300 text-gray-500 hover:bg-gray-50'}`}
            aria-label="Toggle filters"
          >
            <Filter className="w-5 h-5" />
          </button>
        </form>

        {showFilters && (
          <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-100">
            <select
              value={selectedCategory}
              onChange={(e) => updateFilter('category', e.target.value)}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="">All Categories</option>
              {CATEGORIES.map(c => (
                <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
              ))}
            </select>
            <select
              value={selectedPriority}
              onChange={(e) => updateFilter('priority', e.target.value)}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="">All Priorities</option>
              {PRIORITIES.map(p => (
                <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
              ))}
            </select>
            {(selectedCategory || selectedPriority) && (
              <button
                onClick={() => {
                  setSelectedCategory('');
                  setSelectedPriority('');
                  const params = new URLSearchParams(searchParams.toString());
                  params.delete('category');
                  params.delete('priority');
                  router.push(`/dashboard/emails?${params.toString()}`);
                }}
                className="px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 rounded-lg"
              >
                Clear filters
              </button>
            )}
          </div>
        )}
      </div>

      {/* Email List */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center">
            <div className="animate-spin w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full mx-auto"></div>
            <p className="text-gray-500 mt-3">Loading emails...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-red-500">{error}</div>
        ) : !data?.items.length ? (
          <div className="p-12 text-center">
            <Inbox className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">No emails found</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {data.items.map((email) => (
              <Link
                key={email.id}
                href={`/dashboard/emails/${email.id}`}
                className={`flex items-start gap-3 p-4 hover:bg-gray-50 transition-colors ${
                  !email.is_read ? 'bg-primary-50/50' : ''
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {!email.is_read && <span className="w-2 h-2 bg-primary-500 rounded-full flex-shrink-0" />}
                    <p className={`truncate ${!email.is_read ? 'font-semibold text-gray-900' : 'font-medium text-gray-700'}`}>
                      {email.subject || '(No subject)'}
                    </p>
                  </div>
                  <p className="text-sm text-gray-500 truncate mt-0.5">
                    {email.from_name} &lt;{email.from_address}&gt;
                  </p>
                  <p className="text-sm text-gray-400 truncate mt-0.5">{email.preview}</p>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    {email.category && (
                      <span className={`px-2 py-0.5 text-xs rounded-full ${getCategoryColor(email.category)}`}>
                        {email.category}
                      </span>
                    )}
                    {email.priority && (
                      <span className={`px-2 py-0.5 text-xs rounded-full ${getPriorityColor(email.priority)}`}>
                        {email.priority}
                      </span>
                    )}
                    {email.is_urgent && (
                      <span className="px-2 py-0.5 text-xs bg-red-100 text-red-700 rounded-full flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" /> Urgent
                      </span>
                    )}
                    {email.has_attachments && (
                      <Paperclip className="w-3.5 h-3.5 text-gray-400" />
                    )}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1 flex-shrink-0">
                  <span className="text-xs text-gray-400">
                    {new Date(email.received_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </span>
                  {email.is_starred && <Star className="w-4 h-4 text-amber-500 fill-current" />}
                </div>
              </Link>
            ))}
          </div>
        )}

        {/* Pagination */}
        {data && data.pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
            <p className="text-sm text-gray-500">
              Page {data.page} of {data.pages} ({data.total} total)
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => goToPage(data.page - 1)}
                disabled={!data.has_previous}
                className="p-2 rounded-lg border border-gray-300 text-gray-600 hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
                aria-label="Previous page"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => goToPage(data.page + 1)}
                disabled={!data.has_next}
                className="p-2 rounded-lg border border-gray-300 text-gray-600 hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
                aria-label="Next page"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}