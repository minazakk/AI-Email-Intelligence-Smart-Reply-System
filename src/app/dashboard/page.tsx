'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { 
  Mail, 
  MessageSquare, 
  AlertTriangle, 
  Star, 
  Archive, 
  Trash2,
  TrendingUp,
  Clock,
  CheckCircle,
  XCircle
} from 'lucide-react';
import { dashboardApi } from '@/lib/api';
import { DashboardSummary, DashboardCounters, ActivityPoint, CategoryCount } from '@/types/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, AreaChart, Area } from 'recharts';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

function StatCard({ title, value, icon: Icon, href, color = 'primary', trend }: { 
  title: string; 
  value: number | string; 
  icon: React.ComponentType<{ className?: string }>;
  href?: string;
  color?: 'primary' | 'green' | 'amber' | 'red' | 'purple';
  trend?: string;
}) {
  const colorClasses = {
    primary: 'bg-primary-50 text-primary-700 border-primary-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    purple: 'bg-purple-50 text-purple-700 border-purple-200',
  };
  
  const content = (
    <div className="p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{value}</p>
          {trend && <p className="text-sm text-green-600 mt-1">{trend}</p>}
        </div>
        <div className={`p-3 rounded-xl ${colorClasses[color]}`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
    </div>
  );
  
  if (href) {
    return (
      <Link href={href} className="block hover:shadow-md transition-shadow">
        {content}
      </Link>
    );
  }
  
  return <div className="bg-white rounded-xl border border-gray-200">{content}</div>;
}

function ActivityChart({ data }: { data: ActivityPoint[] }) {
  if (!data.length) return <div className="h-64 flex items-center justify-center text-gray-400">No data</div>;
  
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data.slice(-30)}>
          <defs>
            <linearGradient id="activity-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis 
            dataKey="date" 
            tick={{ fontSize: 11, fill: '#9ca3af' }}
            tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            interval="preserveStartEnd"
          />
          <YAxis 
            tick={{ fontSize: 11, fill: '#9ca3af' }}
            tickFormatter={(value) => value >= 1000 ? `${(value/1000).toFixed(1)}k` : value}
          />
          <Tooltip 
            contentStyle={{ backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
            labelFormatter={(value) => new Date(String(value)).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
          />
          <Area 
            type="monotone" 
            dataKey="count" 
            stroke="#3b82f6" 
            strokeWidth={2}
            fillOpacity={1}
            fill="url(#activity-gradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function CategoryChart({ data }: { data: CategoryCount[] }) {
  if (!data.length) return <div className="h-64 flex items-center justify-center text-gray-400">No data</div>;
  
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis type="number" tick={{ fontSize: 11, fill: '#9ca3af' }} />
          <YAxis 
            dataKey="category" 
            type="category" 
            width={100}
            tick={{ fontSize: 11, fill: '#9ca3af' }}
          />
          <Tooltip 
            contentStyle={{ backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
            formatter={(value) => [String(value), 'emails']}
          />
          <Bar 
            dataKey="count" 
            fill="#3b82f6"
            radius={[0, 4, 4, 0]}
            maxBarSize={32}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [activity, setActivity] = useState<ActivityPoint[]>([]);
  const [categories, setCategories] = useState<CategoryCount[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);
        const [summaryData, activityData, categoriesData] = await Promise.all([
          dashboardApi.summary(),
          dashboardApi.activity(30),
          dashboardApi.categories(),
        ]);
        setSummary(summaryData);
        setActivity(activityData);
        setCategories(categoriesData);
      } catch (err) {
        setError('Failed to load dashboard data');
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, []);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => (
            <div key={i} className="bg-white rounded-xl border border-gray-200 p-6 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/4 mb-2"></div>
              <div className="h-8 bg-gray-200 rounded w-1/2"></div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6 h-80 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/4 mb-4"></div>
            <div className="h-full bg-gray-200 rounded"></div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-6 h-80 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/4 mb-4"></div>
            <div className="h-full bg-gray-200 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <XCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
        <h2 className="text-lg font-medium text-gray-900">Failed to load dashboard</h2>
        <p className="text-gray-500 mt-1">{error}</p>
      </div>
    );
  }

  const counters = summary?.counters || {
    total: 0, unread: 0, starred: 0, archived: 0, urgent: 0, reply_required: 0, action_required: 0
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-500 mt-1">Overview of your email intelligence</p>
        </div>
        <Link 
          href="/dashboard/emails" 
          className="bg-primary-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-primary-700 transition-colors flex items-center gap-2"
        >
          <Mail className="w-4 h-4" />
          View Inbox
        </Link>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard 
          title="Total Emails" 
          value={counters.total} 
          icon={Mail} 
          href="/dashboard/emails"
          color="primary"
        />
        <StatCard 
          title="Unread" 
          value={counters.unread} 
          icon={MessageSquare} 
          href="/dashboard/emails?unread=true"
          color="primary"
        />
        <StatCard 
          title="Urgent" 
          value={counters.urgent} 
          icon={AlertTriangle} 
          href="/dashboard/emails?urgent=true"
          color="red"
        />
        <StatCard 
          title="Reply Required" 
          value={counters.reply_required} 
          icon={MessageSquare} 
          href="/dashboard/emails?reply_required=true"
          color="amber"
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard 
          title="Starred" 
          value={counters.starred} 
          icon={Star} 
          href="/dashboard/emails?starred=true"
          color="amber"
        />
        <StatCard 
          title="Archived" 
          value={counters.archived} 
          icon={Archive} 
          href="/dashboard/emails?archived=true"
          color="purple"
        />
        <StatCard 
          title="Trash" 
          value={counters.action_required} 
          icon={Trash2} 
          href="/dashboard/emails?deleted=true"
          color="red"
        />
        <StatCard 
          title="Action Required" 
          value={counters.action_required} 
          icon={CheckCircle} 
          href="/dashboard/emails?action_required=true"
          color="green"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Email Activity (30 days)</h2>
          <ActivityChart data={activity} />
        </div>
        
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Categories</h2>
          <CategoryChart data={categories} />
        </div>
      </div>

      {/* Recent Emails & Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Recent Emails</h2>
            <Link href="/dashboard/emails" className="text-sm text-primary-600 hover:text-primary-500">View all</Link>
          </div>
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {summary?.recent_emails?.slice(0, 8).map((email) => (
              <Link 
                key={email.id} 
                href={`/dashboard/emails/${email.id}`}
                className="block p-3 rounded-lg hover:bg-gray-50 transition-colors border border-transparent hover:border-gray-200"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-gray-900 truncate">{email.subject || '(No subject)'}</p>
                    <p className="text-sm text-gray-500 truncate">{email.from_name} &lt;{email.from_address}&gt;</p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {email.is_urgent && <span className="px-2 py-0.5 text-xs bg-red-100 text-red-700 rounded-full">Urgent</span>}
                    {email.is_starred && <Star className="w-4 h-4 text-amber-500 fill-current" />}
                    <span className="text-xs text-gray-400 whitespace-nowrap">
                      {new Date(email.received_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    </span>
                  </div>
                </div>
              </Link>
            ))}
            {!summary?.recent_emails?.length && (
              <p className="text-gray-500 text-center py-8">No emails yet</p>
            )}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Recent AI Activity</h2>
            <Link href="/dashboard/emails" className="text-sm text-primary-600 hover:text-primary-500">View all</Link>
          </div>
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {summary?.recent_activity?.slice(0, 8).map((activity) => (
              <div key={activity.id} className="p-3 rounded-lg hover:bg-gray-50 transition-colors border border-gray-100">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-primary-100 rounded-full flex items-center justify-center">
                      <CheckCircle className="w-4 h-4 text-primary-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">AI Analysis Completed</p>
                      <p className="text-xs text-gray-500">Email #{activity.email_id}</p>
                    </div>
                  </div>
                  <span className="text-xs text-gray-400">
                    {new Date(activity.created_at).toLocaleString()}
                  </span>
                </div>
              </div>
            ))}
            {!summary?.recent_activity?.length && (
              <p className="text-gray-500 text-center py-8">No recent activity</p>
            )}
          </div>
        </div>
      </div>

      {/* Deadlines */}
      {summary?.deadlines?.length && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <Clock className="w-5 h-5 text-amber-500" />
              Upcoming Deadlines
            </h2>
          </div>
          <div className="space-y-3">
            {summary.deadlines.slice(0, 5).map((deadline) => (
              <div key={deadline.id} className="flex items-center justify-between p-3 rounded-lg bg-gray-50 border border-gray-100">
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full ${deadline.is_overdue ? 'bg-red-500' : 'bg-amber-500'}`} />
                  <div>
                    <p className="font-medium text-gray-900">{deadline.subject}</p>
                    <p className="text-sm text-gray-500">{deadline.entity_type} • Due {new Date(deadline.due_at).toLocaleDateString()}</p>
                  </div>
                </div>
                {deadline.is_overdue && (
                  <span className="px-2 py-1 text-xs bg-red-100 text-red-700 rounded-full">Overdue</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}