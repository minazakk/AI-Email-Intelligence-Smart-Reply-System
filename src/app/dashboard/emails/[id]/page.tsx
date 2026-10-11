'use client';

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { emailApi, replyApi } from '@/lib/api';
import { EmailDetail, SuggestedReplyOut, ReplyTone } from '@/types/api';
import { ArrowLeft, Star, Archive, Trash2, RefreshCw, Paperclip, Bot, Check, X, Edit3, Sparkles, Clock, User, AlertTriangle } from 'lucide-react';

const TONES: { value: ReplyTone; label: string }[] = [
  { value: 'professional', label: 'Professional' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'concise', label: 'Concise' },
  { value: 'empathetic', label: 'Empathetic' },
  { value: 'firm', label: 'Firm' },
];

export default function EmailDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [email, setEmail] = useState<EmailDetail | null>(null);
  const [replies, setReplies] = useState<SuggestedReplyOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedTone, setSelectedTone] = useState<ReplyTone>('professional');
  const [editingReply, setEditingReply] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [error, setError] = useState('');

  const fetchEmail = async () => {
    setIsLoading(true);
    try {
      const data = await emailApi.get(parseInt(id));
      setEmail(data);
      if (data.analysis) {
        const replyData = await replyApi.list({ email_id: data.id });
        setReplies(replyData.items);
      }
    } catch (err) {
      setError('Failed to load email');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchEmail();
  }, [id]);

  const handleGenerateReply = async () => {
    setIsGenerating(true);
    try {
      await replyApi.create(parseInt(id), { tone: selectedTone });
      await fetchEmail();
    } catch (err) {
      setError('Failed to generate reply');
      console.error(err);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleUpdateState = async (field: 'is_read' | 'is_starred' | 'is_archived', value: boolean) => {
    try {
      const updated = await emailApi.updateState(parseInt(id), { [field]: value });
      setEmail(updated);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Move this email to trash?')) return;
    try {
      await emailApi.delete(parseInt(id));
      router.push('/dashboard/emails');
    } catch (err) {
      console.error(err);
    }
  };

  const handleApproveReply = async (replyId: number) => {
    try {
      await replyApi.update(replyId, { status: 'approved' });
      setReplies(prev => prev.map(r => r.id === replyId ? { ...r, status: 'approved' as const } : r));
    } catch (err) {
      console.error(err);
    }
  };

  const handleRejectReply = async (replyId: number) => {
    try {
      await replyApi.update(replyId, { status: 'rejected' });
      setReplies(prev => prev.map(r => r.id === replyId ? { ...r, status: 'rejected' as const } : r));
    } catch (err) {
      console.error(err);
    }
  };

  const handleSaveEdit = async (replyId: number) => {
    try {
      await replyApi.update(replyId, { body: editText });
      setReplies(prev => prev.map(r => r.id === replyId ? { ...r, body: editText, is_edited: true } : r));
      setEditingReply(null);
    } catch (err) {
      console.error(err);
    }
  };

  const getPriorityColor = (priority: string | null) => {
    switch (priority) {
      case 'critical': return 'bg-red-100 text-red-700 border-red-200';
      case 'high': return 'bg-orange-100 text-orange-700 border-orange-200';
      case 'normal': return 'bg-blue-100 text-blue-700 border-blue-200';
      case 'low': return 'bg-gray-100 text-gray-700 border-gray-200';
      default: return 'bg-gray-100 text-gray-600 border-gray-200';
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full"></div>
      </div>
    );
  }

  if (error || !email) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500">{error || 'Email not found'}</p>
        <Link href="/dashboard/emails" className="text-primary-600 hover:underline mt-2 inline-block">Back to inbox</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Link href="/dashboard/emails" className="flex items-center gap-2 text-gray-600 hover:text-gray-900">
          <ArrowLeft className="w-5 h-5" />
          Back to inbox
        </Link>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleUpdateState('is_starred', !email.is_starred)}
            className={`p-2 rounded-lg ${email.is_starred ? 'text-amber-500 bg-amber-50' : 'text-gray-400 hover:bg-gray-100'}`}
            aria-label="Toggle star"
          >
            <Star className={`w-5 h-5 ${email.is_starred ? 'fill-current' : ''}`} />
          </button>
          <button
            onClick={() => handleUpdateState('is_archived', !email.is_archived)}
            className={`p-2 rounded-lg ${email.is_archived ? 'text-primary-500 bg-primary-50' : 'text-gray-400 hover:bg-gray-100'}`}
            aria-label="Toggle archive"
          >
            <Archive className="w-5 h-5" />
          </button>
          <button
            onClick={handleDelete}
            className="p-2 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50"
            aria-label="Delete"
          >
            <Trash2 className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Email Content */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="p-6 border-b border-gray-100">
          <h1 className="text-xl font-bold text-gray-900">{email.subject || '(No subject)'}</h1>
          <div className="flex items-center gap-4 mt-3 text-sm text-gray-500">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-primary-100 rounded-full flex items-center justify-center">
                <User className="w-4 h-4 text-primary-600" />
              </div>
              <div>
                <p className="font-medium text-gray-900">{email.from_name || email.from_address}</p>
                <p className="text-xs">{email.from_address}</p>
              </div>
            </div>
            <span className="text-gray-300">|</span>
            <div className="flex items-center gap-1">
              <Clock className="w-4 h-4" />
              {new Date(email.received_at).toLocaleString()}
            </div>
          </div>
          {email.has_attachments && (
            <div className="flex items-center gap-2 mt-3 text-sm text-gray-500">
              <Paperclip className="w-4 h-4" />
              {email.attachment_names.join(', ')}
            </div>
          )}
        </div>

        {/* AI Analysis */}
        {email.analysis && (
          <div className="p-6 border-b border-gray-100 bg-gray-50">
            <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <Bot className="w-4 h-4 text-primary-500" />
              AI Analysis
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <p className="text-xs text-gray-500">Category</p>
                <p className="font-medium text-gray-900 capitalize">{email.analysis.category}</p>
              </div>
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <p className="text-xs text-gray-500">Priority</p>
                <span className={`inline-block px-2 py-0.5 text-xs rounded-full border ${getPriorityColor(email.analysis.priority)}`}>
                  {email.analysis.priority}
                </span>
              </div>
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <p className="text-xs text-gray-500">Sentiment</p>
                <p className="font-medium text-gray-900 capitalize">{email.analysis.sentiment}</p>
              </div>
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <p className="text-xs text-gray-500">Intent</p>
                <p className="font-medium text-gray-900">{email.analysis.intent}</p>
              </div>
            </div>
            <div className="space-y-2">
              <div>
                <p className="text-xs text-gray-500 mb-1">Summary</p>
                <p className="text-sm text-gray-700">{email.analysis.summary_short}</p>
              </div>
              {email.analysis.key_points.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1">Key Points</p>
                  <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                    {email.analysis.key_points.map((point, i) => (
                      <li key={i}>{point}</li>
                    ))}
                  </ul>
                </div>
              )}
              {email.analysis.reply_required && (
                <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 px-3 py-2 rounded-lg">
                  <AlertTriangle className="w-4 h-4" />
                  Reply required
                </div>
              )}
            </div>
          </div>
        )}

        {/* Email Body */}
        <div className="p-6">
          <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap">
            {email.body_text}
          </div>
        </div>
      </div>

      {/* Smart Replies */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary-500" />
            Smart Replies
          </h2>
          <div className="flex items-center gap-2">
            <select
              value={selectedTone}
              onChange={(e) => setSelectedTone(e.target.value as ReplyTone)}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              {TONES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <button
              onClick={handleGenerateReply}
              disabled={isGenerating}
              className="px-4 py-1.5 bg-primary-600 text-white text-sm rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
            >
              {isGenerating ? (
                <div className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full"></div>
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              Generate
            </button>
          </div>
        </div>

        {replies.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No replies generated yet. Click Generate to create one.</p>
        ) : (
          <div className="space-y-4">
            {replies.map((reply) => (
              <div key={reply.id} className={`border rounded-lg p-4 ${
                reply.status === 'approved' ? 'border-green-200 bg-green-50' :
                reply.status === 'rejected' ? 'border-red-200 bg-red-50' :
                'border-gray-200'
              }`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-500 capitalize">{reply.tone}</span>
                    {reply.is_edited && <span className="text-xs text-gray-400">(edited)</span>}
                    {reply.status !== 'draft' && (
                      <span className={`px-2 py-0.5 text-xs rounded-full ${
                        reply.status === 'approved' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                      }`}>
                        {reply.status}
                      </span>
                    )}
                  </div>
                  {reply.status === 'draft' && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => { setEditingReply(reply.id); setEditText(reply.body); }}
                        className="p-1.5 rounded text-gray-400 hover:text-primary-600 hover:bg-primary-50"
                        aria-label="Edit reply"
                      >
                        <Edit3 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleApproveReply(reply.id)}
                        className="p-1.5 rounded text-gray-400 hover:text-green-600 hover:bg-green-50"
                        aria-label="Approve reply"
                      >
                        <Check className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleRejectReply(reply.id)}
                        className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50"
                        aria-label="Reject reply"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
                {editingReply === reply.id ? (
                  <div className="space-y-2">
                    <textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      className="w-full p-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 min-h-[100px]"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleSaveEdit(reply.id)}
                        className="px-3 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setEditingReply(null)}
                        className="px-3 py-1.5 text-gray-600 text-sm rounded-lg hover:bg-gray-100"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">{reply.body}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}