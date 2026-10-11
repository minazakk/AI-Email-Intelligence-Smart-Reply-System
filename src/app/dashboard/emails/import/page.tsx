'use client';

import { useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { emailApi } from '@/lib/api';
import { ImportSummary } from '@/types/api';
import { Upload, FileText, File, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

export default function ImportPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<ImportSummary | null>(null);
  const [error, setError] = useState('');
  const [processWithAi, setProcessWithAi] = useState(true);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length) await uploadFiles(files);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length) await uploadFiles(files);
  };

  const uploadFiles = async (files: File[]) => {
    setIsUploading(true);
    setError('');
    setResult(null);

    try {
      const isEml = files.every(f => f.name.endsWith('.eml'));
      const isCsv = files.every(f => f.name.endsWith('.csv'));
      const isJson = files.every(f => f.name.endsWith('.json'));

      if (isEml) {
        const summary = await emailApi.importEml(files);
        setResult(summary);
      } else if (isCsv || isJson) {
        const summary = await emailApi.importDataset(files[0], processWithAi);
        setResult(summary);
      } else {
        setError('Unsupported file format. Use .eml, .csv, or .json');
      }
    } catch (err) {
      setError('Import failed. Please try again.');
      console.error(err);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Import Emails</h1>
        <p className="text-gray-500 mt-1">Upload .eml files or CSV/JSON datasets</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {result && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="flex items-center gap-2 text-green-700 font-medium mb-2">
            <CheckCircle className="w-5 h-5" />
            Import Complete
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-white rounded-lg p-3 border border-green-100">
              <p className="text-gray-500">Created</p>
              <p className="text-xl font-bold text-green-700">{result.created}</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-green-100">
              <p className="text-gray-500">Duplicates</p>
              <p className="text-xl font-bold text-gray-700">{result.duplicates}</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-green-100">
              <p className="text-gray-500">Failed</p>
              <p className="text-xl font-bold text-red-600">{result.failed}</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-green-100">
              <p className="text-gray-500">Total Received</p>
              <p className="text-xl font-bold text-gray-700">{result.received}</p>
            </div>
          </div>
          {result.errors.length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-medium text-gray-700 mb-1">Errors:</p>
              <ul className="text-sm text-red-600 space-y-1">
                {result.errors.slice(0, 5).map((err, i) => (
                  <li key={i}>Row {err.row}: {err.message}</li>
                ))}
              </ul>
            </div>
          )}
          <button
            onClick={() => router.push('/dashboard/emails')}
            className="mt-4 px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700"
          >
            View Imported Emails
          </button>
        </div>
      )}

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
          isDragging ? 'border-primary-500 bg-primary-50' : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
        <p className="text-lg font-medium text-gray-900">Drop files here or click to browse</p>
        <p className="text-sm text-gray-500 mt-1">Supports .eml, .csv, .json</p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".eml,.csv,.json"
          onChange={handleFileSelect}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="mt-4 px-6 py-2 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50"
        >
          {isUploading ? (
            <span className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Uploading...
            </span>
          ) : (
            'Select Files'
          )}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={processWithAi}
            onChange={(e) => setProcessWithAi(e.target.checked)}
            className="w-4 h-4 text-primary-600 rounded border-gray-300 focus:ring-primary-500"
          />
          <div>
            <p className="text-sm font-medium text-gray-900">Process with AI</p>
            <p className="text-xs text-gray-500">Run AI analysis on imported emails (category, priority, sentiment)</p>
          </div>
        </label>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h3 className="text-sm font-medium text-gray-900 mb-2">File Format Guidelines</h3>
        <div className="space-y-2 text-sm text-gray-600">
          <div className="flex items-start gap-2">
            <FileText className="w-4 h-4 text-blue-500 mt-0.5" />
            <p><strong>.eml</strong> — Standard email format (one or more files)</p>
          </div>
          <div className="flex items-start gap-2">
            <File className="w-4 h-4 text-green-500 mt-0.5" />
            <p><strong>.csv</strong> — Columns: subject, from_address, from_name, body_text, received_at</p>
          </div>
          <div className="flex items-start gap-2">
            <File className="w-4 h-4 text-purple-500 mt-0.5" />
            <p><strong>.json</strong> — Array of email objects with same fields as CSV</p>
          </div>
        </div>
      </div>
    </div>
  );
}