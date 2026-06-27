// frontend/app/results/[id]/page.tsx

import ReactMarkdown from "react-markdown";
import { notFound } from "next/navigation";

async function getResults(id: string) {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const res = await fetch(`${API_URL}/results/${id}`, {
    cache: "no-store",
  });
  return res.json();
}

// Await params — required in Next.js 15+
export default async function ResultsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  if (!id || id === "undefined") {
    notFound();
  }

  const data = await getResults(id);

  if (data.status === "not_found") {
    notFound();
  }

  return (
    <main className="max-w-4xl mx-auto p-8 space-y-10">
      <h1 className="text-3xl font-bold">Your Job Search Results</h1>

      {/* Jobs found */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Jobs Found</h2>
        <div className="grid gap-4">
          {data.jobs_list?.map((job: any, i: number) => (
            <div key={i} className="border rounded-lg p-4">
              <h3 className="font-semibold">{job.job_title}</h3>
              <p className="text-gray-600">
                {job.company_name} · {job.company_location}
              </p>
              <a
                href={job.job_url}
                target="_blank"
                className="text-blue-600 text-sm hover:underline"
              >
                View posting →
              </a>
            </div>
          ))}
        </div>
      </section>

      {/* Skills report */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Skills Required</h2>
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown>{data.skills_report}</ReactMarkdown>
        </div>
      </section>

      {/* Prep guide */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Your Preparation Roadmap</h2>
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown>{data.prep_guide}</ReactMarkdown>
        </div>
      </section>
    </main>
  );
}