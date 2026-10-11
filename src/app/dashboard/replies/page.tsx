'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { replyApi } from '@/lib/api';
import { SuggestedReplyOut, ReplyStatus } from '@/types/api';
import { MessageSquare, Check, X, Edit3, Trash2, ChevronLeft, ChevronRight } from 'lucide-react';

const STATUS_FILTERS: { value: ReplyStatus | ''; label: string }[] = [
  { value: '', label: 'All' },
  { value: 'draft', label: 'Drafts' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
];

export default function RepliesPage() {
  const [replies, setReplies] = useState<SuggestedReplyOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<ReplyStatus | ''>('');
  const [isLoading, setIsLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState('');

  const fetchReplies = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await replyApi.list({
        page,
        page_size: 20,
        status: status || undefined,
      });
      setReplies(data.items);
      setTotal(data.total);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [page, status]);

  useEffect(() => {
    fetchReplies();
  }, [fetchReplies]);

  const handleStatusChange = async (id: number, newStatus: ReplyStatus) => {
    try {
      await replyApi.update(id, { status: newStatus });
      setReplies(prev => prev.map(r => r.id === id ? { ...r, status: newStatus } : r));
    } catch (err) {
      console.error(err);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this reply?')) return;
    try {
      await replyApi.delete(id);
      setReplies(prev => prev.filter(r => r.id !== id));
    } catch (err) {
      console.error(err);
    }
  };

  const handleSaveEdit = async (id: number) => {
    try {
      await replyApi.update(id, { body: editText });
      setReplies(prev => prev.map(r => r.id === id ? { ...r, body: editText, is_edited: true } : r));
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const pages = Math.ceil(total / 20);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Smart Replies</h1>
        <p className="text-gray-500 mt-1">{total} replies</p>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        {STATUS_FILTERS.map(f => (
          <button
            key={f.value}
            onClick={() => { setStatus(f.value); setPage(1); }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              status === f.value
                ? 'bg-primary-600 text-white'
                : 'bg-white border border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Replies List */}
      <div className="space-y-4">
        {isLoading ? (
          <div className="text-center py-12">
            <div className="animate-spin w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full mx-auto"></div>
          </div>
        ) : replies.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
            <MessageSquare className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">No replies found</p>
          </div>
        ) : (
          replies.map((reply) => (
            <div key={reply.id} className="bg-white rounded-xl border border-gray-200 p-6">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded-full capitalize">{reply.tone}</span>
                  <span className={`px-2 py-0.5 text-xs rounded-full ${
                    reply.status === 'approved' ? 'bg-green-100 text-green-700' :
                    reply.status === 'rejected' ? 'bg-red-100 text-red-700' :
                    'bg-blue-100 text-blue-700'
                  }`}>
                    {reply.status}
                  </span>
                  {reply.is_edited && <span className="text-xs text-gray-400">(edited)</span>}
                </div>
                <div className="flex items-center gap-1">
                  {reply.status === 'draft' && (
                    <>
                      <Link
                        href={`/dashboard/emails/${reply.email_id}`}
                        className="p-1.5 rounded text-gray-400 hover:text-primary-600 hover:bg-primary-50"
                        aria-label="View email"
                      >
                        <MessageSquare className="w-4 h-4" />
                      </Link>
                      <button
                        onClick={() => { setEditingId(reply.id); setEditText(reply.body); }}
                        className="p-1.5 rounded text-gray-400 hover:text-primary-600 hover:bg-primary-50"
                        aria-label="Edit"
                      >
                        <Edit3 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleStatusChange(reply.id, 'approved')}
                        className="p-1.5 rounded text-gray-400 hover:text-green-600 hover:bg-green-50"
                        aria-label="Approve"
                      >
                        <Check className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleStatusChange(reply.id, 'rejected')}
                        className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50"
                        aria-label="Reject"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => handleDelete(reply.id)}
                    className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50"
                    aria-label="Delete"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {editingId === reply.id ? (
                <div className="space-y-2">
                  <textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    className="w-full p-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 min-h-[120px]"
                  />
                  <div className="flex gap-2">
                    <button onClick={() => handleSaveEdit(reply.id)} className="px-3 py-1.5 bg-primary-600 text-white text-sm rounded-lg">Save</button>
                    <button onClick={() => setEditingId(null)} className="px-3 py-1.5 text-gray-600 text-sm rounded-lg hover:bg-gray-100">Cancel</button>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{reply.body}</p>
              )}

              <p className="text-xs text-gray-400 mt-3">
                Created {new Date(reply.created_at).toLocaleString()}
              </p>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="p-2 rounded-lg border border-gray-300 text-gray-600 hover:bg-white disabled:opacity-50"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-sm text-gray-600">Page {page} of {pages}</span>
          <button
            onClick={() => setPage(p => Math.min(pages, p + 1))}
            disabled={page === pages}
            className="p-2 rounded-lg border border-gray-300 text-gray-600 hover:bg-white disabled:opacity-50"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}