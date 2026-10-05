'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { emailApi } from '@/lib/api';
import { Send, Loader2 } from 'lucide-react';

export default function ComposePage() {
  const router = useRouter();
  const [formData, setFormData] = useState({
    to: '',
    subject: '',
    body_text: '',
  });
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormData(prev => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.to.trim() || !formData.body_text.trim()) {
      setError('Please fill in the recipient and message');
      return;
    }

    setIsSending(true);
    setError('');

    try {
      await emailApi.create({
        to: formData.to.split(',').map(e => e.trim()).filter(Boolean),
        subject: formData.subject,
        body_text: formData.body_text,
        from_address: 'me@localhost',
        direction: 'outbound',
        process_with_ai: false,
      });
      router.push('/dashboard/emails');
    } catch (err) {
      setError('Failed to send email');
      console.error(err);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Compose Email</h1>
        <p className="text-gray-500 mt-1">Create and send a new email</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">To</label>
          <input
            type="text"
            name="to"
            value={formData.to}
            onChange={handleChange}
            placeholder="recipient@example.com"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Subject</label>
          <input
            type="text"
            name="subject"
            value={formData.subject}
            onChange={handleChange}
            placeholder="Email subject"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Message</label>
          <textarea
            name="body_text"
            value={formData.body_text}
            onChange={handleChange}
            placeholder="Write your message..."
            rows={12}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 resize-none"
            required
          />
        </div>

        <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
          <button
            type="button"
            onClick={() => router.back()}
            className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isSending}
            className="flex items-center gap-2 px-6 py-2 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50"
          >
            {isSending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {isSending ? 'Sending...' : 'Send'}
          </button>
        </div>
      </form>
    </div>
  );
}