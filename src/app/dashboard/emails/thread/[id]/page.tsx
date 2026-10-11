'use client';

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { emailApi } from '@/lib/api';
import { ThreadDetail } from '@/types/api';
import { ArrowLeft, User, Clock, Bot } from 'lucide-react';

export default function ThreadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchThread = async () => {
      setIsLoading(true);
      try {
        const data = await emailApi.getThread(parseInt(id));
        setThread(data);
      } catch (err) {
        setError('Failed to load thread');
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchThread();
  }, [id]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full"></div>
      </div>
    );
  }

  if (error || !thread) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500">{error || 'Thread not found'}</p>
        <Link href="/dashboard/emails" className="text-primary-600 hover:underline mt-2 inline-block">Back to inbox</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link href="/dashboard/emails" className="flex items-center gap-2 text-gray-600 hover:text-gray-900">
        <ArrowLeft className="w-5 h-5" />
        Back to inbox
      </Link>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="p-6 border-b border-gray-100">
          <h1 className="text-xl font-bold text-gray-900">{thread.subject}</h1>
          <p className="text-sm text-gray-500 mt-1">{thread.message_count} messages</p>
        </div>

        <div className="divide-y divide-gray-100">
          {thread.messages.map((message) => (
            <div key={message.id} className="p-6">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 bg-primary-100 rounded-full flex items-center justify-center flex-shrink-0">
                  <User className="w-5 h-5 text-primary-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-gray-900">{message.from_name || message.from_address}</p>
                      <p className="text-sm text-gray-500">{message.from_address}</p>
                    </div>
                    <div className="flex items-center gap-2 text-sm text-gray-400">
                      <Clock className="w-4 h-4" />
                      {new Date(message.received_at).toLocaleString()}
                    </div>
                  </div>

                  {message.category && (
                    <span className="inline-block px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded-full mt-2">
                      {message.category}
                    </span>
                  )}

                  <div className="mt-3 text-sm text-gray-700 whitespace-pre-wrap">
                    {message.body_text}
                  </div>

                  {message.summary_short && (
                    <div className="mt-3 p-3 bg-blue-50 rounded-lg border border-blue-100">
                      <p className="text-xs font-medium text-blue-700 flex items-center gap-1">
                        <Bot className="w-3 h-3" />
                        AI Summary
                      </p>
                      <p className="text-sm text-blue-800 mt-1">{message.summary_short}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}