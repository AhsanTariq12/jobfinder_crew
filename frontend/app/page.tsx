"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    job_role: "",
    location: "United States of America",
    job_type: "Remote",
    company: "",
  });

  async function handleSubmit() {
    setLoading(true);
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const res = await fetch(`${API_URL}/api/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const data = await res.json();
    router.push(`/search/${data.job_id}`);
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold mb-2">JobHunt Crew</h1>
      <p className="text-gray-500 mb-8">AI-powered job research & interview prep</p>

      <div className="w-full max-w-md space-y-4">
        <input
          className="w-full border rounded-lg p-3"
          placeholder="Job role (e.g. Full Stack Developer)"
          value={form.job_role}
          onChange={e => setForm(f => ({ ...f, job_role: e.target.value }))}
        />
        <input
          className="w-full border rounded-lg p-3"
          placeholder="Location"
          value={form.location}
          onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
        />
        <select
          className="w-full border rounded-lg p-3"
          value={form.job_type}
          onChange={e => setForm(f => ({ ...f, job_type: e.target.value }))}
        >
          <option>Remote</option>
          <option>Hybrid</option>
          <option>On-site</option>
        </select>
        <input
          className="w-full border rounded-lg p-3"
          placeholder="Company (optional)"
          value={form.company}
          onChange={e => setForm(f => ({ ...f, company: e.target.value }))}
        />
        <button
          onClick={handleSubmit}
          disabled={!form.job_role || loading}
          className="w-full bg-blue-600 text-white rounded-lg p-3 font-medium
                     hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Starting search..." : "Find Jobs & Prepare"}
        </button>
      </div>
    </main>
  );
}